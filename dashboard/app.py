"""FastAPI dashboard entry point. Run with: uvicorn dashboard.app:app"""
import os
import secrets
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from config import Settings
from dashboard.discord_api import DiscordAPI
from storage import GuildStorage


BASE_DIR = Path(__file__).resolve().parent
settings = Settings.from_env()
client_id = os.getenv("DISCORD_CLIENT_ID")
client_secret = os.getenv("DISCORD_CLIENT_SECRET")
redirect_uri = os.getenv("DISCORD_REDIRECT_URI")
session_secret = os.getenv("SESSION_SECRET")
if not all((client_id, client_secret, redirect_uri, session_secret)):
    raise RuntimeError("Dashboard OAuth settings are missing. Configure .env from .env.example.")

storage = GuildStorage(settings.database_path)
api = DiscordAPI(settings.discord_token, client_id, client_secret, redirect_uri)
app = FastAPI(title="Tueka Dashboard")
app.add_middleware(SessionMiddleware, secret_key=session_secret, https_only=os.getenv("DASHBOARD_HTTPS_ONLY", "true").lower() == "true", same_site="lax")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def session_token(request: Request) -> str:
    session_id = request.session.get("session_id")
    token = storage.dashboard_session_token(session_id) if session_id else None
    if not token:
        raise HTTPException(status_code=401, detail="ログインが必要です")
    return token


async def authorized(request: Request, guild_id: int) -> str:
    token = session_token(request)
    if not await api.can_manage(token, guild_id):
        raise HTTPException(status_code=403, detail="このサーバーを管理する権限がありません")
    return token


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return RedirectResponse("/servers" if session_token_or_none(request) else "/login", status_code=303)


def session_token_or_none(request: Request) -> str | None:
    session_id = request.session.get("session_id")
    return storage.dashboard_session_token(session_id) if session_id else None


@app.get("/login")
async def login(request: Request):
    state = secrets.token_urlsafe(32)
    request.session.clear()
    request.session["oauth_state"] = state
    params = urlencode({"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": "identify guilds", "state": state})
    return RedirectResponse(f"https://discord.com/oauth2/authorize?{params}", status_code=303)


@app.get("/oauth/callback")
async def oauth_callback(request: Request, code: str | None = None, state: str | None = None):
    if not code or not state or not secrets.compare_digest(state, request.session.get("oauth_state", "")):
        raise HTTPException(status_code=400, detail="OAuth state が無効です")
    try:
        token_data = await api.exchange_code(code)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Discordログインに失敗しました") from exc
    request.session.clear()
    session_id = secrets.token_urlsafe(32)
    storage.create_dashboard_session(session_id, token_data["access_token"], int(token_data.get("expires_in", 604800)))
    request.session["session_id"] = session_id
    request.session["csrf_token"] = secrets.token_urlsafe(32)
    return RedirectResponse("/servers", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    session_id = request.session.get("session_id")
    if session_id:
        storage.delete_dashboard_session(session_id)
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@app.get("/servers", response_class=HTMLResponse)
async def servers(request: Request):
    try:
        guilds = await api.manageable_guilds(session_token(request))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Discordセッションの再認証が必要です") from exc
    return templates.TemplateResponse(request, "servers.html", {"guilds": guilds})


@app.get("/servers/{guild_id}/settings", response_class=HTMLResponse)
async def guild_settings(request: Request, guild_id: int):
    token = await authorized(request, guild_id)
    channels, roles = await api.guild_resources(guild_id)
    return templates.TemplateResponse(request, "settings.html", {"guild_id": guild_id, "settings": storage.get_settings(guild_id), "channels": channels, "roles": roles, "csrf_token": request.session["csrf_token"]})


def optional_id(value: str) -> int | None:
    return int(value) if value else None


@app.post("/servers/{guild_id}/settings")
async def save_guild_settings(request: Request, guild_id: int, csrf_token: str = Form(), management_channel_id: str = Form(""), welcome_channel_id: str = Form(""), default_role_id: str = Form("")):
    if not secrets.compare_digest(csrf_token, request.session.get("csrf_token", "")):
        raise HTTPException(status_code=403, detail="CSRF検証に失敗しました")
    await authorized(request, guild_id)
    channels, roles = await api.guild_resources(guild_id)
    channel_ids, role_ids = {int(item["id"]) for item in channels}, {int(item["id"]) for item in roles}
    try:
        management, welcome, role = optional_id(management_channel_id), optional_id(welcome_channel_id), optional_id(default_role_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="ID形式が不正です") from exc
    if (management is not None and management not in channel_ids) or (welcome is not None and welcome not in channel_ids) or (role is not None and role not in role_ids):
        raise HTTPException(status_code=422, detail="選択値はこのサーバーのリソースではありません")
    storage.update_settings(guild_id, management_channel_id=management, welcome_channel_id=welcome, default_role_id=role)
    return RedirectResponse(f"/servers/{guild_id}/settings?saved=1", status_code=303)
