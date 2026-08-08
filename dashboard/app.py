"""FastAPI dashboard entry point. Run with: uvicorn dashboard.app:app"""
import os
import secrets
from pathlib import Path
from urllib.parse import urlencode
from asyncio import gather

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from config import Settings
from dashboard.discord_api import DiscordAPI
from feature_registry import FEATURES, get_feature
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


def avatar_url(user: dict) -> str:
    avatar = user.get("avatar")
    if avatar:
        return f"https://cdn.discordapp.com/avatars/{user['id']}/{avatar}.png?size=128"
    index = (int(user["id"]) >> 22) % 6
    return f"https://cdn.discordapp.com/embed/avatars/{index}.png"


def guild_icon_url(guild: dict) -> str | None:
    icon = guild.get("icon")
    return f"https://cdn.discordapp.com/icons/{guild['id']}/{icon}.png?size=128" if icon else None


async def page_identity(token: str) -> dict:
    user, bot_user = await gather(api.current_user(token), api.bot_user())
    return {"current_user": {"name": user.get("global_name") or user["username"], "avatar_url": avatar_url(user)}, "bot": {"name": bot_user["username"], "avatar_url": avatar_url(bot_user)}}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    bot_user = await api.bot_user()
    return templates.TemplateResponse(request, "landing.html", {"bot": {"name": bot_user["username"], "avatar_url": avatar_url(bot_user)}, "authenticated": bool(session_token_or_none(request))})


def session_token_or_none(request: Request) -> str | None:
    session_id = request.session.get("session_id")
    return storage.dashboard_session_token(session_id) if session_id else None


@app.get("/login")
async def login(request: Request):
    state = secrets.token_urlsafe(32)
    request.session.clear()
    storage.create_oauth_state(state)
    params = urlencode({"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": "identify guilds", "state": state})
    return RedirectResponse(f"https://discord.com/oauth2/authorize?{params}", status_code=303)


@app.get("/oauth/callback")
async def oauth_callback(request: Request, code: str | None = None, state: str | None = None):
    if not code or not state or not storage.consume_oauth_state(state):
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


@app.get("/api/identity")
async def identity(request: Request):
    return await page_identity(session_token(request))


@app.exception_handler(404)
async def not_found(request: Request, exc):
    try:
        bot_user = await api.bot_user()
        bot = {"name": bot_user["username"], "avatar_url": avatar_url(bot_user)}
    except Exception:
        bot = {"name": "Tueka", "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png"}
    return templates.TemplateResponse(request, "404.html", {"bot": bot}, status_code=404)


@app.get("/servers", response_class=HTMLResponse)
async def servers(request: Request):
    try:
        token = session_token(request)
        guilds, identity = await gather(api.manageable_guilds(token), page_identity(token))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Discordセッションの再認証が必要です") from exc
    for guild in guilds:
        guild["icon_url"] = guild_icon_url(guild)
    return templates.TemplateResponse(request, "servers.html", {"guilds": guilds, **identity})


def feature_view(guild_id: int, feature):
    module = storage.get_module(guild_id, feature.id)
    return {"definition": feature, "enabled": module["enabled"], "settings": module["settings"]}


@app.get("/servers/{guild_id}", response_class=HTMLResponse)
async def guild_home(request: Request, guild_id: int):
    token = await authorized(request, guild_id)
    cards = [feature_view(guild_id, feature) for feature in FEATURES]
    categories = {"community": [card for card in cards if card["definition"].category == "community"], "moderation": [card for card in cards if card["definition"].category == "moderation"]}
    return templates.TemplateResponse(request, "guild_home.html", {"guild_id": guild_id, "categories": categories, "csrf_token": request.session["csrf_token"], **(await page_identity(token))})


@app.get("/servers/{guild_id}/settings")
async def legacy_guild_settings(guild_id: int):
    return RedirectResponse(f"/servers/{guild_id}", status_code=303)


@app.get("/servers/{guild_id}/modules/{module_id}", response_class=HTMLResponse)
async def module_settings(request: Request, guild_id: int, module_id: str):
    token = await authorized(request, guild_id)
    try:
        feature = get_feature(module_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="機能が見つかりません") from exc
    channels, roles = await api.guild_resources(guild_id)
    module = feature_view(guild_id, feature)
    draft_key = f"{guild_id}:{module_id}"
    drafts = request.session.get("module_drafts", {})
    draft = drafts.get(draft_key) if request.query_params.get("error") else None
    if draft:
        module["enabled"] = draft["enabled"]
        module["settings"].update(draft["settings"])
    elif draft_key in drafts:
        drafts.pop(draft_key)
        request.session["module_drafts"] = drafts
    return templates.TemplateResponse(request, "module_settings.html", {"guild_id": guild_id, "module": module, "channels": channels, "roles": roles, "csrf_token": request.session["csrf_token"], **(await page_identity(token))})


@app.get("/favicon.ico")
async def favicon():
    return RedirectResponse(avatar_url(await api.bot_user()), status_code=307)


def optional_id(value: str) -> int | None:
    return int(value) if value else None


@app.post("/servers/{guild_id}/modules/{module_id}")
async def save_module_settings(request: Request, guild_id: int, module_id: str, csrf_token: str = Form(), enabled: str | None = Form(None), management_channel_id: str = Form(""), welcome_channel_id: str = Form(""), default_role_id: str = Form("")):
    target = f"/servers/{guild_id}/modules/{module_id}"
    if not secrets.compare_digest(csrf_token, request.session.get("csrf_token", "")):
        return RedirectResponse(f"{target}?error=csrf", status_code=303)
    await authorized(request, guild_id)
    try:
        feature = get_feature(module_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="機能が見つかりません")
    channels, roles = await api.guild_resources(guild_id)
    channel_ids, role_ids = {int(item["id"]) for item in channels}, {int(item["id"]) for item in roles}
    try:
        management, welcome, role = optional_id(management_channel_id), optional_id(welcome_channel_id), optional_id(default_role_id)
    except ValueError:
        return RedirectResponse(f"{target}?error=invalid-selection", status_code=303)
    if (management is not None and management not in channel_ids) or (welcome is not None and welcome not in channel_ids) or (role is not None and role not in role_ids):
        return RedirectResponse(f"{target}?error=invalid-selection", status_code=303)
    values = {"management_channel_id": management, "welcome_channel_id": welcome, "default_role_id": role}
    draft_key = f"{guild_id}:{module_id}"
    drafts = request.session.get("module_drafts", {})
    drafts[draft_key] = {"enabled": enabled == "on", "settings": {field: values[field] for field in feature.fields}}
    if enabled == "on" and any(values[field] is None for field in feature.fields):
        request.session["module_drafts"] = drafts
        return RedirectResponse(f"{target}?error=setup-required", status_code=303)
    module = storage.get_module(guild_id, module_id)
    for field in feature.fields:
        module["settings"][field] = values[field]
    storage.set_module(guild_id, module_id, enabled=enabled == "on", settings=module["settings"])
    # Keep the legacy columns current for safe backward compatibility.
    if module_id == "welcome":
        storage.update_settings(guild_id, welcome_channel_id=module["settings"].get("welcome_channel_id"), default_role_id=module["settings"].get("default_role_id"))
    if module_id == "audit_log":
        storage.update_settings(guild_id, management_channel_id=module["settings"].get("management_channel_id"))
    drafts.pop(draft_key, None)
    request.session["module_drafts"] = drafts
    return RedirectResponse(f"{target}?saved=1", status_code=303)
