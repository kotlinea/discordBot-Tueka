"""FastAPI dashboard entry point. Run with: uvicorn dashboard.app:app"""
import os
import json
import secrets
import time
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from pathlib import Path
import re
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from config import Settings
from dashboard.repository import DashboardRepository
from dashboard.discord_api import DiscordAPI
from dashboard.timing import add as add_timing, begin as begin_timing, end as end_timing
from social import SocialRepository
from social.crypto import SocialTokenCipher
from social.webhooks import verify_twitch_signature, verify_youtube_signature
from dashboard.api_v1 import create_api_router
from dashboard.api.dependencies import ApiDependencies
from observability.heartbeat import ServiceHeartbeat
from observability.http import router as health_router, observe_request
from observability.logging import configure_logging
from observability.configuration import thresholds


BASE_DIR = Path(__file__).resolve().parent
settings = Settings.from_env()
configure_logging('dashboard', settings.log_level)
client_id = os.getenv("DISCORD_CLIENT_ID")
client_secret = os.getenv("DISCORD_CLIENT_SECRET")
redirect_uri = os.getenv("DISCORD_REDIRECT_URI")
session_secret = os.getenv("SESSION_SECRET")
if not all((client_id, client_secret, redirect_uri, session_secret)):
    raise RuntimeError("Dashboard OAuth settings are missing. Configure .env from .env.example.")

social_repository = SocialRepository(settings.database_url)
dashboard_repository = DashboardRepository(settings.database_url)
api = DiscordAPI(settings.discord_token, client_id, client_secret, redirect_uri)
access_dependencies = ApiDependencies(dashboard_repository, api)
social_cipher = SocialTokenCipher(settings.social_token_encryption_key)


@asynccontextmanager
async def dashboard_lifespan(_: FastAPI):
    await api.start()
    try:
        async with ServiceHeartbeat('dashboard', settings.database_url):
            yield
    finally:
        await api.close()


app = FastAPI(
    title="Tueka Dashboard",
    lifespan=dashboard_lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)
app.add_middleware(SessionMiddleware, secret_key=session_secret, https_only=os.getenv("DASHBOARD_HTTPS_ONLY", "true").lower() == "true", same_site="lax")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
FRONTEND_DIST = Path(os.getenv("TUEKA_FRONTEND_DIST", str(BASE_DIR / "frontend" / "dist")))
app.mount("/ui", StaticFiles(directory=FRONTEND_DIST, check_dir=False), name="dashboard-v2")
DOCS_DIST = Path(os.getenv("TUEKA_DOCS_DIST", str(BASE_DIR.parent / "docs" / ".vitepress" / "dist")))
app.include_router(health_router(settings.database_url, (FRONTEND_DIST, DOCS_DIST), os.getenv('MONITORING_TOKEN'),
    **thresholds()))
app.middleware('http')(observe_request)
app.mount("/docs", StaticFiles(directory=DOCS_DIST, html=True, check_dir=False), name="documentation")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
app.include_router(create_api_router(settings.database_url, api, settings))


def spa_response():
    index = FRONTEND_DIST / 'index.html'
    if not index.is_file():
        raise HTTPException(503, detail='Dashboard assets are missing. Build dashboard/frontend before starting the dashboard.')
    return FileResponse(index, headers={'Cache-Control': 'no-cache, must-revalidate'})


@app.get('/servers', include_in_schema=False)
async def server_picker():
    return spa_response()


@app.get('/servers/{guild_id}', include_in_schema=False)
@app.get('/servers/{guild_id}/{route:path}', include_in_schema=False)
async def dashboard_page(guild_id: int, route: str = ''):
    # Only current SPA routes receive the shell. Obsolete form/JSON URLs are gone.
    from feature_registry import get_feature
    valid = route in {'', 'settings', 'suggestions'}
    valid |= bool(re.fullmatch(r'moderation(?:/(?:automod|anti_spam|anti_raid|infractions|moderation_actions|moderation_logs)(?:/rules(?:/(?:new|\d+))?)?)?', route))
    valid |= bool(re.fullmatch(r'social(?:/(?:youtube|twitch|x|tiktok|instagram))?', route))
    valid |= bool(re.fullmatch(r'tickets(?:/(?:inbox(?:/\d+)?|forms|teams|settings|transcripts|tags|stats|panel-messages|panels(?:/(?:new|\d+))?))?', route))
    valid |= bool(re.fullmatch(r'reaction-roles(?:/(?:new|\d+))?', route))
    if route.startswith('modules/'):
        module_id = route.removeprefix('modules/')
        try:
            feature = get_feature(module_id)
        except ValueError:
            raise HTTPException(404, detail='Dashboard route not found')
        valid = feature is not None and module_id not in {'tickets', 'reaction_roles', 'suggestions'} and feature.category != 'social'
    if not valid:
        raise HTTPException(404, detail='Dashboard route not found')
    return spa_response()


@app.get('/tickets/transcripts/{transcript_id}', include_in_schema=False)
async def transcript_page(transcript_id: str):
    return spa_response()


@app.exception_handler(HTTPException)
async def http_exception_response(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/v1"):
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": exc.status_code,
                "code": str(detail.get("code", "request_failed")),
                "detail": str(detail.get("message", "リクエストを処理できませんでした。")),
                "errors": detail.get("errors", []),
            },
            headers=exc.headers,
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


@app.get("/tokens.css", include_in_schema=False)
async def design_tokens():
    return FileResponse(BASE_DIR.parent / "tokens.css", media_type="text/css")


@app.middleware("http")
async def server_timing(request: Request, call_next):
    started, token = time.perf_counter(), begin_timing()
    try:
        response = await call_next(request)
    finally:
        metrics = end_timing(token)
    total = (time.perf_counter() - started) * 1000
    response.headers["Server-Timing"] = f"app;dur={total:.1f}, discord;dur={metrics['discord_ms']:.1f}, template;dur={metrics['template_ms']:.1f}"
    if request.url.path.startswith("/docs/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable" if "/assets/" in request.url.path else "public, max-age=300, must-revalidate"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


def render_page(request: Request, name: str, context: dict, status_code: int = 200):
    started = time.perf_counter()
    try:
        return templates.TemplateResponse(request, name, context, status_code=status_code)
    finally:
        add_timing("template_ms", (time.perf_counter() - started) * 1000)


def session_token(request: Request) -> str:
    try:
        return access_dependencies.token(request)
    except HTTPException as exc:
        raise HTTPException(status_code=401, detail="ログインが必要です") from exc


async def authorized(request: Request, guild_id: int, *, live: bool = False) -> str:
    try:
        return await access_dependencies.manage(request, guild_id, live=live)
    except HTTPException as exc:
        message = "ログインが必要です" if exc.status_code == 401 else "このサーバーを管理する権限がありません"
        raise HTTPException(status_code=exc.status_code, detail=message) from exc


def avatar_url(user: dict) -> str:
    avatar = user.get("avatar")
    if avatar:
        return f"https://cdn.discordapp.com/avatars/{user['id']}/{avatar}.png?size=128"
    index = (int(user["id"]) >> 22) % 6
    return f"https://cdn.discordapp.com/embed/avatars/{index}.png"


def frontend_css_url() -> str | None:
    manifest_path = FRONTEND_DIST / ".vite" / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        css = json.loads(manifest_path.read_text(encoding="utf-8")).get("index.html", {}).get("css", [])
        return f"/ui/{css[0]}" if css else None
    except (OSError, ValueError):
        return None


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    bot_user = await api.bot_user()
    return render_page(request, "landing.html", {"bot": {"name": bot_user["username"], "avatar_url": avatar_url(bot_user)}, "authenticated": bool(session_token_or_none(request)), "frontend_css": frontend_css_url()})


def session_token_or_none(request: Request) -> str | None:
    return access_dependencies.token_or_none(request)


@app.get("/login")
async def login(request: Request):
    state = secrets.token_urlsafe(32)
    request.session.clear()
    dashboard_repository.create_oauth_state(state)
    params = urlencode({"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": "identify guilds", "state": state})
    return RedirectResponse(f"https://discord.com/oauth2/authorize?{params}", status_code=303)


@app.get("/oauth/callback")
async def oauth_callback(request: Request, code: str | None = None, state: str | None = None):
    if not code or not state or not dashboard_repository.consume_oauth_state(state):
        raise HTTPException(status_code=400, detail="OAuth state が無効です")
    try:
        token_data = await api.exchange_code(code)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Discordログインに失敗しました") from exc
    request.session.clear()
    session_id = secrets.token_urlsafe(32)
    dashboard_repository.create_dashboard_session(session_id, token_data["access_token"], int(token_data.get("expires_in", 604800)))
    request.session["session_id"] = session_id
    request.session["csrf_token"] = secrets.token_urlsafe(32)
    return RedirectResponse("/servers", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    session_id = request.session.get("session_id")
    if session_id:
        dashboard_repository.delete_dashboard_session(session_id)
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@app.exception_handler(404)
async def not_found(request: Request, exc):
    try:
        bot_user = await api.bot_user()
        bot = {"name": bot_user["username"], "avatar_url": avatar_url(bot_user)}
    except Exception:
        bot = {"name": "Tueka", "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png"}
    return render_page(request, "404.html", {"bot": bot, "frontend_css": frontend_css_url()}, status_code=404)


@app.post("/social/oauth/{provider}/connect/{guild_id}")
async def begin_social_connection(request: Request, guild_id: int, provider: str):
    form = await request.form()
    target = f"/servers/{guild_id}/social/{provider}" if provider in {"tiktok", "instagram"} else f"/servers/{guild_id}"
    if not access_dependencies.valid_csrf(request, form.get("csrf_token")):
        return RedirectResponse(f"{target}?error=csrf", status_code=303)
    await authorized(request, guild_id, live=True)
    if not social_cipher.available:
        return RedirectResponse(f"{target}?error=social-token-key", status_code=303)
    state = secrets.token_urlsafe(32)
    if provider == "tiktok" and settings.tiktok_client_key and settings.tiktok_redirect_uri:
        social_repository.create_social_oauth_state(state, guild_id, provider)
        params = urlencode({"client_key": settings.tiktok_client_key, "response_type": "code", "scope": "user.info.basic,video.list", "redirect_uri": settings.tiktok_redirect_uri, "state": state})
        return RedirectResponse(f"https://www.tiktok.com/v2/auth/authorize/?{params}", status_code=303)
    if provider == "instagram" and settings.instagram_app_id and settings.instagram_redirect_uri:
        social_repository.create_social_oauth_state(state, guild_id, provider)
        params = urlencode({"client_id": settings.instagram_app_id, "redirect_uri": settings.instagram_redirect_uri, "response_type": "code", "scope": "instagram_business_basic", "state": state})
        return RedirectResponse(f"https://www.instagram.com/oauth/authorize?{params}", status_code=303)
    return RedirectResponse(f"{target}?error=social-provider-unavailable", status_code=303)


@app.get("/social/oauth/{provider}/callback")
async def social_oauth_callback(provider: str, code: str | None = None, state: str | None = None, error: str | None = None):
    if not state or error:
        raise HTTPException(status_code=400, detail="ソーシャルOAuth認証が拒否されました")
    guild_id = social_repository.consume_social_oauth_state(state, provider)
    if guild_id is None or not code:
        raise HTTPException(status_code=400, detail="ソーシャルOAuth state が無効です")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if provider == "tiktok" and settings.tiktok_client_key and settings.tiktok_client_secret and settings.tiktok_redirect_uri:
                response = await client.post("https://open.tiktokapis.com/v2/oauth/token/", data={"client_key": settings.tiktok_client_key, "client_secret": settings.tiktok_client_secret, "code": code, "grant_type": "authorization_code", "redirect_uri": settings.tiktok_redirect_uri})
                payload = response.raise_for_status().json()
                token = payload.get("access_token")
                account_id = payload.get("open_id")
                account_name = payload.get("scope", "TikTok account")
            elif provider == "instagram" and settings.instagram_app_id and settings.instagram_app_secret and settings.instagram_redirect_uri:
                response = await client.post("https://api.instagram.com/oauth/access_token", data={"client_id": settings.instagram_app_id, "client_secret": settings.instagram_app_secret, "grant_type": "authorization_code", "redirect_uri": settings.instagram_redirect_uri, "code": code})
                payload = response.raise_for_status().json()
                token = payload.get("access_token")
                account_id = str(payload.get("user_id", ""))
                account_name = "Instagram Professional account"
            else:
                raise ValueError("Provider credentials are not configured")
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="ソーシャルOAuthトークンの取得に失敗しました") from exc
    if not token or not account_id:
        raise HTTPException(status_code=502, detail="ソーシャルOAuthの応答が不完全です")
    social_repository.save_social_connection(guild_id, provider, str(account_id), str(account_name), social_cipher.encrypt(str(token)), social_cipher.encrypt(str(payload["refresh_token"])) if payload.get("refresh_token") else None, int(time.time()) + int(payload.get("expires_in", 0)) if payload.get("expires_in") else None)
    return RedirectResponse(f"/servers/{guild_id}/social/{provider}?saved=connected", status_code=303)


@app.get("/favicon.ico")
async def favicon():
    return RedirectResponse(avatar_url(await api.bot_user()), status_code=307)


@app.get("/webhooks/youtube")
async def youtube_webhook_verify(request: Request):
    """WebSub lease validation; the public callback URL is configured at YouTube."""
    if request.query_params.get("hub.mode") == "denied":
        topic = request.query_params.get("hub.topic", "")
        channel_id = parse_qs(urlparse(topic).query).get("channel_id", [""])[0]
        if channel_id:
            social_repository.invalidate_social_target("youtube", channel_id, request.query_params.get("hub.reason", "WebSub subscription denied"))
    return PlainTextResponse(request.query_params.get("hub.challenge", ""))


@app.post("/webhooks/youtube")
async def youtube_webhook(request: Request):
    body = await request.body()
    if len(body) > 1_000_000:
        raise HTTPException(status_code=413, detail="Webhook payload is too large")
    if settings.social_webhook_secret:
        supplied = request.headers.get("x-hub-signature", "")
        if not verify_youtube_signature(body, supplied, settings.social_webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid YouTube webhook signature")
    try:
        root = ET.fromstring(body)
        namespaces = {"yt": "http://www.youtube.com/xml/schemas/2015", "atom": "http://www.w3.org/2005/Atom"}
        video_id = root.findtext(".//yt:videoId", namespaces=namespaces)
        account_id = root.findtext(".//yt:channelId", namespaces=namespaces)
        title = root.findtext(".//atom:title", namespaces=namespaces) or "YouTube video"
    except ET.ParseError:
        raise HTTPException(status_code=400, detail="Invalid YouTube webhook payload")
    if not video_id or not account_id:
        raise HTTPException(status_code=400, detail="YouTube event is incomplete")
    social_repository.wake_social_target("youtube", account_id)
    return PlainTextResponse("ok")


@app.post("/webhooks/twitch")
async def twitch_webhook(request: Request):
    body = await request.body()
    if len(body) > 1_000_000 or not settings.social_webhook_secret:
        raise HTTPException(status_code=401 if not settings.social_webhook_secret else 413, detail="Twitch webhook is not configured")
    message_id = request.headers.get("twitch-eventsub-message-id", "")
    timestamp = request.headers.get("twitch-eventsub-message-timestamp", "")
    supplied = request.headers.get("twitch-eventsub-message-signature", "")
    if not verify_twitch_signature(body, message_id, timestamp, supplied, settings.social_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid Twitch webhook signature")
    payload = json.loads(body)
    message_type = request.headers.get("twitch-eventsub-message-type", "")
    if message_type == "webhook_callback_verification":
        return PlainTextResponse(str(payload.get("challenge", "")))
    if message_type == "revocation":
        condition = (payload.get("subscription") or {}).get("condition") or {}
        account = str(condition.get("broadcaster_user_id", ""))
        if account:
            social_repository.invalidate_social_target("twitch", account, str((payload.get("subscription") or {}).get("status") or "EventSub subscription revoked"))
        return PlainTextResponse("ok")
    event, subscription = payload.get("event") or {}, payload.get("subscription") or {}
    raw_type = str(subscription.get("type", ""))
    event_type = "live_start" if raw_type == "stream.online" else "live_end" if raw_type == "stream.offline" else ""
    account_id = str(event.get("broadcaster_user_id", ""))
    if not event_type or not account_id:
        raise HTTPException(status_code=400, detail="Unsupported Twitch event")
    external_id = str(event.get("id") or message_id)
    handle = str(event.get("broadcaster_user_login", ""))
    social_repository.enqueue_social_event_v2("twitch", external_id, account_id, event_type, {
        "account": event.get("broadcaster_user_name") or handle, "handle": handle, "title": event.get("title") or "配信を開始しました",
        "text": "", "url": f"https://twitch.tv/{handle}", "platform": "Twitch", "event": event_type, "type": event_type,
        "published_at": event.get("started_at", ""), "thumbnail": "", "avatar": "", "viewer_count": "",
    })
    return PlainTextResponse("ok")
