"""FastAPI dashboard entry point. Run with: uvicorn dashboard.app:app"""
import os
import json
import secrets
import time
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlencode
from asyncio import gather

import httpx

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from config import Settings
from dashboard.discord_api import DiscordAPI, ADMINISTRATOR, PERMISSION_BITS
from dashboard.icon_registry import get_icon
from dashboard.timing import add as add_timing, begin as begin_timing, end as end_timing
from feature_registry import FEATURES, get_feature, japanese_copy
from storage import GuildStorage
from social_crypto import SocialTokenCipher
from automod import ACTION_TYPES, TRIGGER_TYPES, AutoModEngine, MessageContext, default_rule, validate_rule
from dashboard.api_v1 import create_api_router


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
social_cipher = SocialTokenCipher(settings.social_token_encryption_key)


@asynccontextmanager
async def dashboard_lifespan(_: FastAPI):
    await api.start()
    try:
        yield
    finally:
        await api.close()


app = FastAPI(title="Tueka Dashboard", lifespan=dashboard_lifespan)
app.add_middleware(SessionMiddleware, secret_key=session_secret, https_only=os.getenv("DASHBOARD_HTTPS_ONLY", "true").lower() == "true", same_site="lax")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
app.mount("/ui", StaticFiles(directory=FRONTEND_DIST, check_dir=False), name="dashboard-v2")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
app.include_router(create_api_router(storage, api))


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


def dashboard_v2_enabled(path: str) -> bool:
    if os.getenv("DASHBOARD_UI_V2", "false").lower() != "true" or not path.startswith("/servers"):
        return False
    allowlist = {value.strip() for value in os.getenv("DASHBOARD_UI_V2_GUILDS", "").split(",") if value.strip()}
    parts = path.strip("/").split("/")
    return not allowlist or len(parts) == 1 or (len(parts) > 1 and parts[1] in allowlist)


@app.middleware("http")
async def server_timing(request: Request, call_next):
    started, token = time.perf_counter(), begin_timing()
    try:
        if request.method == "GET" and dashboard_v2_enabled(request.url.path) and (FRONTEND_DIST / "index.html").exists():
            # Authentication remains authoritative in /api/v1/session.  This
            # middleware intentionally does not read request.session because
            # SessionMiddleware may be inside the timing middleware stack.
            response = FileResponse(FRONTEND_DIST / "index.html")
        else:
            response = await call_next(request)
    finally:
        metrics = end_timing(token)
    total = (time.perf_counter() - started) * 1000
    response.headers["Server-Timing"] = f"app;dur={total:.1f}, discord;dur={metrics['discord_ms']:.1f}, template;dur={metrics['template_ms']:.1f}"
    return response


def render_page(request: Request, name: str, context: dict, status_code: int = 200):
    started = time.perf_counter()
    try:
        return templates.TemplateResponse(request, name, context, status_code=status_code)
    finally:
        add_timing("template_ms", (time.perf_counter() - started) * 1000)


def session_token(request: Request) -> str:
    session_id = request.session.get("session_id")
    token = storage.dashboard_session_token(session_id) if session_id else None
    if not token:
        raise HTTPException(status_code=401, detail="ログインが必要です")
    return token


async def authorized(request: Request, guild_id: int, *, live: bool = False) -> str:
    token = session_token(request)
    if not await api.can_manage(token, guild_id, use_cache=not live):
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


def frontend_css_url() -> str | None:
    manifest_path = FRONTEND_DIST / ".vite" / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        css = json.loads(manifest_path.read_text(encoding="utf-8")).get("index.html", {}).get("css", [])
        return f"/ui/{css[0]}" if css else None
    except (OSError, ValueError):
        return None


def social_provider_available(provider: str) -> bool:
    return {
        "youtube": bool(settings.youtube_api_key),
        "twitch": bool(settings.twitch_client_id and settings.twitch_client_secret),
        "tiktok": bool(settings.tiktok_client_key and settings.tiktok_client_secret and settings.tiktok_redirect_uri and social_cipher.available),
        "x": bool(settings.x_bearer_token),
        "instagram": bool(settings.instagram_app_id and settings.instagram_app_secret and settings.instagram_redirect_uri and social_cipher.available),
    }.get(provider, False)


SOCIAL_MODULE_PROVIDERS = {"youtube_updates": "youtube", "twitch_updates": "twitch", "tiktok_updates": "tiktok", "x_updates": "x", "instagram_updates": "instagram"}
MODERATION_SECTIONS = ("automod", "anti_spam", "anti_raid", "infractions", "moderation_actions", "moderation_logs")
FAMILY_TRIGGERS = {
    "automod": ("keyword", "regex", "safe_browsing", "phishing_link", "discord_invite", "domain", "caps", "emoji_sticker_rate", "media_only", "honeypot"),
    "anti_spam": ("message_rate", "duplicate", "mention_rate", "link_rate", "attachment_rate", "reaction_rate", "reaction_burst"),
    "anti_raid": ("join_rate", "leave_rate", "new_account_ratio", "new_member_activity"),
}


async def subscribe_youtube_websub(channel_id: str) -> bool:
    """Register a public channel at the official WebSub hub.

    A new subscription only receives notifications published after this point;
    it never backfills existing videos into Discord.
    """
    if not settings.dashboard_base_url:
        return False
    callback = f"{settings.dashboard_base_url.rstrip('/')}/webhooks/youtube"
    data = {"hub.mode": "subscribe", "hub.topic": f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}", "hub.callback": callback, "hub.verify": "async"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post("https://pubsubhubbub.appspot.com/subscribe", data=data)
            return response.status_code in {202, 204}
    except httpx.HTTPError:
        return False


async def page_identity(token: str) -> dict:
    user, bot_user = await gather(api.current_user(token), api.bot_user())
    return {"current_user": {"id": int(user["id"]), "name": user.get("global_name") or user["username"], "avatar_url": avatar_url(user)}, "bot": {"name": bot_user["username"], "avatar_url": avatar_url(bot_user)}}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    bot_user = await api.bot_user()
    return render_page(request, "landing.html", {"bot": {"name": bot_user["username"], "avatar_url": avatar_url(bot_user)}, "authenticated": bool(session_token_or_none(request)), "frontend_css": frontend_css_url()})


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


@app.exception_handler(404)
async def not_found(request: Request, exc):
    try:
        bot_user = await api.bot_user()
        bot = {"name": bot_user["username"], "avatar_url": avatar_url(bot_user)}
    except Exception:
        bot = {"name": "Tueka", "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png"}
    return render_page(request, "404.html", {"bot": bot, "frontend_css": frontend_css_url()}, status_code=404)


@app.get("/servers", response_class=HTMLResponse)
async def servers(request: Request):
    try:
        token = session_token(request)
        guilds, identity = await gather(api.manageable_guilds(token), page_identity(token))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Discordセッションの再認証が必要です") from exc
    for guild in guilds:
        guild["icon_url"] = guild_icon_url(guild)
    return render_page(request, "servers.html", {"guilds": guilds, **identity})


def feature_view(guild_id: int, feature, bot_permissions: int | None = None):
    module = storage.get_module(guild_id, feature.id)
    missing = [] if bot_permissions is None or bot_permissions & ADMINISTRATOR else [permission for permission in feature.required_bot_permissions if not bot_permissions & PERMISSION_BITS[permission]]
    if feature.id == "audit_log" and module["settings"].get("log_member") and bot_permissions is not None and not bot_permissions & ADMINISTRATOR and not bot_permissions & PERMISSION_BITS["view_audit_log"]:
        missing.append("view_audit_log")
    title, description = japanese_copy(feature.id)
    return {"definition": feature, "icon": get_icon(feature.icon), "enabled": module["enabled"], "settings": module["settings"], "missing_permissions": missing, "title": title, "description": description}


@app.get("/servers/{guild_id}", response_class=HTMLResponse)
async def guild_home(request: Request, guild_id: int):
    token = await authorized(request, guild_id)
    _, _, bot_permissions = await api.guild_resources(guild_id)
    cards = [feature_view(guild_id, feature, bot_permissions) for feature in FEATURES if feature.parent is None]
    categories = {category: [card for card in cards if card["definition"].category == category] for category in ("community", "moderation", "social")}
    return render_page(request, "guild_home.html", {"guild_id": guild_id, "categories": categories, "csrf_token": request.session["csrf_token"], **(await page_identity(token))})


@app.get("/servers/{guild_id}/settings")
async def legacy_guild_settings(guild_id: int):
    return RedirectResponse(f"/servers/{guild_id}", status_code=303)


@app.get("/servers/{guild_id}/moderation", response_class=HTMLResponse)
async def moderation_hub(request: Request, guild_id: int):
    token = await authorized(request, guild_id)
    channels, roles, bot_permissions = await api.guild_resources(guild_id)
    core = feature_view(guild_id, get_feature("moderation"), bot_permissions)
    sections = [feature_view(guild_id, get_feature(item), bot_permissions) for item in MODERATION_SECTIONS]
    return render_page(request, "moderation_hub.html", {"guild_id": guild_id, "module": core, "sections": sections,
        "summary": storage.moderation_summary(guild_id), "events": storage.recent_moderation_events(guild_id, limit=10),
        "lockdown": storage.active_lockdown(guild_id), "channels": channels, "roles": roles,
        "csrf_token": request.session["csrf_token"], **(await page_identity(token))})


@app.get("/servers/{guild_id}/moderation/{section}", response_class=HTMLResponse)
async def moderation_section(request: Request, guild_id: int, section: str):
    if section not in MODERATION_SECTIONS:
        raise HTTPException(status_code=404, detail="Moderation機能が見つかりません")
    token = await authorized(request, guild_id)
    channels, roles, bot_permissions = await api.guild_resources(guild_id)
    module = feature_view(guild_id, get_feature(section), bot_permissions)
    family = section if section in FAMILY_TRIGGERS else None
    rules = storage.moderation_rules(guild_id, family=family) if family else []
    selected = None
    rule_id = request.query_params.get("rule_id")
    if family and rule_id and rule_id.isdigit():
        selected = storage.moderation_rule(guild_id, int(rule_id))
        if selected and selected["family"] != family:
            selected = None
    if family and selected is None:
        selected = default_rule(FAMILY_TRIGGERS[family][0])
        selected["family"] = family
    preview = request.session.pop(f"moderation_preview:{guild_id}:{section}", None)
    user_id = int(request.query_params["user_id"]) if section == "infractions" and request.query_params.get("user_id", "").isdigit() else None
    return render_page(request, "moderation_section.html", {"guild_id": guild_id, "section": section, "module": module,
        "rules": rules, "selected_rule": selected, "trigger_types": FAMILY_TRIGGERS.get(family, ()), "channels": channels,
        "roles": roles, "events": storage.recent_moderation_events(guild_id, family=family, user_id=user_id, limit=50),
        "cases": storage.recent_cases(guild_id, user_id, 50) if user_id else [], "active_points": storage.active_points(guild_id, user_id) if user_id else 0,
        "selected_user_id": user_id, "lockdown": storage.active_lockdown(guild_id),
        "preview": preview,
        "csrf_token": request.session["csrf_token"], **(await page_identity(token))})


@app.get("/servers/{guild_id}/modules/{module_id}", response_class=HTMLResponse)
async def module_settings(request: Request, guild_id: int, module_id: str):
    if module_id in {"chat_filter", "automod", "anti_spam", "anti_raid", "infractions", "moderation_actions", "moderation_logs"}:
        target = "automod" if module_id == "chat_filter" else module_id
        return RedirectResponse(f"/servers/{guild_id}/moderation/{target}", status_code=303)
    if module_id == "audit_log":
        return RedirectResponse(f"/servers/{guild_id}/moderation/moderation_logs", status_code=303)
    if module_id == "moderation":
        return RedirectResponse(f"/servers/{guild_id}/moderation", status_code=303)
    token = await authorized(request, guild_id)
    try:
        feature = get_feature(module_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="機能が見つかりません") from exc
    channels, roles, bot_permissions = await api.guild_resources(guild_id)
    module = feature_view(guild_id, feature, bot_permissions)
    if module_id == "automod":
        rule_id = request.query_params.get("rule_id")
        selected_rule = storage.automod_rule(guild_id, int(rule_id)) if rule_id and rule_id.isdigit() else None
        selected_rule = selected_rule or default_rule()
        preview_key = f"automod_preview:{guild_id}"
        preview = request.session.pop(preview_key, None)
        return render_page(request, "automod.html", {
            "guild_id": guild_id, "module": module, "channels": channels, "roles": roles,
            "rules": storage.automod_rules(guild_id), "selected_rule": selected_rule,
            "trigger_types": sorted(TRIGGER_TYPES), "action_types": sorted(ACTION_TYPES),
            "preview": preview, "csrf_token": request.session["csrf_token"], **(await page_identity(token)),
        })
    draft_key = f"{guild_id}:{module_id}"
    drafts = request.session.get("module_drafts", {})
    draft = drafts.get(draft_key) if request.query_params.get("error") else None
    if draft:
        module["enabled"] = draft["enabled"]
        module["settings"].update(draft["settings"])
    elif draft_key in drafts:
        drafts.pop(draft_key)
        request.session["module_drafts"] = drafts
    social_provider = SOCIAL_MODULE_PROVIDERS.get(module_id)
    subscriptions = storage.social_subscriptions(guild_id, social_provider) if social_provider else []
    connections = {item["provider"] for item in storage.social_connections(guild_id)} if social_provider else set()
    provider_available = {provider: social_provider_available(provider) for provider in ("youtube", "twitch", "tiktok", "x", "instagram")}
    template_name = "social_module_settings.html" if social_provider else "module_settings.html"
    return render_page(request, template_name, {"guild_id": guild_id, "module": module, "social_provider": social_provider, "channels": channels, "roles": roles, "subscriptions": subscriptions, "social_connections": connections, "provider_available": provider_available, "csrf_token": request.session["csrf_token"], **(await page_identity(token))})


def _csrf_ok(request: Request, value: object) -> bool:
    return secrets.compare_digest(str(value or ""), request.session.get("csrf_token", ""))


def _form_ids(values: list[object], allowed: set[int], limit: int = 100) -> list[int]:
    try:
        parsed = list(dict.fromkeys(int(value) for value in values if str(value)))
    except ValueError as exc:
        raise ValueError("invalid resource") from exc
    if len(parsed) > limit or any(value not in allowed for value in parsed):
        raise ValueError("invalid resource")
    return parsed


def _json_object(value: object, fallback: object) -> object:
    text = str(value or "").strip()
    result = json.loads(text) if text else fallback
    if not isinstance(result, type(fallback)):
        raise ValueError("invalid JSON shape")
    return result


def _lines(value: object, limit: int, item_limit: int = 253) -> list[str]:
    return list(dict.fromkeys(item.strip()[:item_limit] for item in str(value or "").splitlines() if item.strip()))[:limit]


def _typed_moderation_rule(form: Any, family: str, allowed_channels: set[int], allowed_roles: set[int]) -> dict:
    trigger = str(form.get("trigger_type", ""))
    if trigger not in FAMILY_TRIGGERS.get(family, ()):
        raise ValueError("invalid family trigger")
    raw = default_rule(trigger)
    config: dict[str, Any] = {}
    if trigger == "keyword":
        config = {"keywords": _lines(form.get("keywords"), 1000, 60), "allow_list": _lines(form.get("allow_list"), 100, 60), "match": str(form.get("keyword_match", "wildcard"))}
    elif trigger == "regex":
        config = {"patterns": _lines(form.get("patterns"), 20, 260)}
    elif trigger == "domain":
        config = {"domains": _lines(form.get("domains"), 500), "mode": str(form.get("domain_mode", "blacklist"))}
    elif trigger in {"message_rate", "duplicate", "mention_rate", "link_rate", "attachment_rate", "reaction_rate", "reaction_burst", "join_rate", "leave_rate", "new_account_ratio", "emoji_sticker_rate"}:
        config = {"limit": form.get("limit", 3), "window_seconds": form.get("window_seconds", 10)}
        if trigger == "duplicate":
            config["similarity_percent"] = form.get("similarity_percent", 100)
        elif trigger == "new_account_ratio":
            config.update({"account_age_days": form.get("account_age_days", 7), "percentage": form.get("percentage", 70)})
        elif trigger == "emoji_sticker_rate":
            config["per_message_limit"] = form.get("per_message_limit", 12)
    elif trigger == "caps":
        config = {"percentage": form.get("percentage", 70), "minimum_letters": form.get("minimum_letters", 6)}
    elif trigger == "new_member_activity":
        config = {"join_age_minutes": form.get("join_age_minutes", 10)}
    elif trigger == "media_only":
        config = {"allow_links": form.get("allow_links") == "on"}
    elif trigger == "honeypot":
        config = {"channel_ids": _form_ids(form.getlist("honeypot_channel_ids"), allowed_channels, 20)}
    raw.update({"name": str(form.get("name", "")), "enabled": form.get("enabled") == "on", "mode": str(form.get("mode", "monitor")),
        "priority": form.get("priority", 100), "stop_on_match": form.get("stop_on_match") == "on", "family": family,
        "trigger_config": config, "conditions": {
            "channel_ids": _form_ids(form.getlist("condition_channel_ids"), allowed_channels),
            "category_ids": _form_ids(form.getlist("condition_category_ids"), allowed_channels),
            "required_role_ids": _form_ids(form.getlist("required_role_ids"), allowed_roles),
            "excluded_role_ids": _form_ids(form.getlist("excluded_role_ids"), allowed_roles),
            "minimum_account_age_days": form.get("minimum_account_age_days", 0), "minimum_join_age_days": form.get("minimum_join_age_days", 0),
            "user_ids": [int(item) for item in _lines(form.get("condition_user_ids"), 100) if item.isdigit()],
            "actor_kinds": form.getlist("actor_kinds"), "bot_ids": [int(item) for item in _lines(form.get("bot_ids"), 100) if item.isdigit()],
            "webhook_ids": [int(item) for item in _lines(form.get("webhook_ids"), 100) if item.isdigit()],
        }, "exemptions": {
            "channel_ids": _form_ids(form.getlist("exempt_channel_ids"), allowed_channels),
            "category_ids": _form_ids(form.getlist("exempt_category_ids"), allowed_channels),
            "role_ids": _form_ids(form.getlist("exempt_role_ids"), allowed_roles),
            "user_ids": [int(item) for item in _lines(form.get("exempt_user_ids"), 100) if item.isdigit()],
            "bot_ids": [int(item) for item in _lines(form.get("exempt_bot_ids"), 100) if item.isdigit()],
            "webhook_ids": [int(item) for item in _lines(form.get("exempt_webhook_ids"), 100) if item.isdigit()],
        }})
    actions: list[dict[str, Any]] = []
    for action_type in form.getlist("actions"):
        action: dict[str, Any] = {"type": str(action_type)}
        if action_type == "points":
            action.update({"points": form.get("points", 1), "expires_days": form.get("expires_days", 30)})
        elif action_type in {"timeout", "tempban"}:
            action["duration_minutes"] = form.get("duration_minutes", 10)
        elif action_type == "notify":
            action.update({"channel_id": form.get("notify_channel_id"), "message": str(form.get("notify_message", "ルール違反を検知しました。"))})
        elif action_type == "dm":
            action["message"] = str(form.get("dm_message", "ルール違反を検知しました: {reason}"))
        elif action_type == "purge":
            action["count"] = form.get("purge_count", 10)
        elif action_type == "lockdown":
            action.update({"duration_minutes": form.get("lockdown_minutes", 30), "channel_ids": _form_ids(form.getlist("lockdown_channel_ids"), allowed_channels)})
        actions.append(action)
    raw["actions"] = actions
    return validate_rule(raw)


@app.post("/servers/{guild_id}/moderation/settings")
async def save_moderation_core(request: Request, guild_id: int):
    form = await request.form()
    target = f"/servers/{guild_id}/moderation"
    if not _csrf_ok(request, form.get("csrf_token")):
        return RedirectResponse(f"{target}?error=csrf", status_code=303)
    await authorized(request, guild_id, live=True)
    channels, roles, _ = await api.guild_resources(guild_id, use_cache=False)
    channel_ids, role_ids = {int(item["id"]) for item in channels}, {int(item["id"]) for item in roles}
    try:
        settings = storage.get_module(guild_id, "moderation")["settings"]
        log_id = int(form["default_log_channel_id"]) if form.get("default_log_channel_id") else None
        if log_id and log_id not in {int(item["id"]) for item in channels if int(item["type"]) == 0}:
            raise ValueError("invalid log channel")
        settings.update({"default_log_channel_id": log_id, "immune_role_ids": _form_ids(form.getlist("immune_role_ids"), role_ids),
            "immune_channel_ids": _form_ids(form.getlist("immune_channel_ids"), channel_ids),
            "evidence_excluded_channel_ids": _form_ids(form.getlist("evidence_excluded_channel_ids"), channel_ids),
            "immune_user_ids": [int(item) for item in _lines(form.get("immune_user_ids"), 100) if item.isdigit()],
            "evidence_retention_days": max(1,min(int(form.get("evidence_retention_days",30)),365)),
            "exclude_bots": form.get("exclude_bots") == "on", "exclude_webhooks": form.get("exclude_webhooks") == "on"})
    except (TypeError, ValueError):
        return RedirectResponse(f"{target}?error=invalid", status_code=303)
    storage.set_module(guild_id, "moderation", enabled=form.get("enabled") == "on", settings=settings)
    return RedirectResponse(f"{target}?saved=1", status_code=303)


@app.post("/servers/{guild_id}/moderation/{section}/settings")
async def save_moderation_section_settings(request: Request, guild_id: int, section: str):
    if section not in MODERATION_SECTIONS:
        raise HTTPException(status_code=404)
    form = await request.form()
    target = f"/servers/{guild_id}/moderation/{section}"
    if not _csrf_ok(request, form.get("csrf_token")):
        return RedirectResponse(f"{target}?error=csrf", status_code=303)
    await authorized(request, guild_id, live=True)
    channels, roles, _ = await api.guild_resources(guild_id, use_cache=False)
    channel_ids, role_ids = {int(item["id"]) for item in channels}, {int(item["id"]) for item in roles}
    settings = storage.get_module(guild_id, section)["settings"]
    try:
        if "immune_role_ids" in settings:
            settings.update({"immune_role_ids": _form_ids(form.getlist("immune_role_ids"), role_ids), "immune_channel_ids": _form_ids(form.getlist("immune_channel_ids"), channel_ids),
                "immune_user_ids": [int(item) for item in _lines(form.get("immune_user_ids"),100) if item.isdigit()]})
        if section == "anti_raid":
            settings["default_lockdown_minutes"] = max(1,min(int(form.get("default_lockdown_minutes",30)),1440))
        if section == "infractions":
            thresholds = []
            for points, action, duration in zip(form.getlist("threshold_points"),form.getlist("threshold_action"),form.getlist("threshold_duration")):
                item = {"points": max(1,min(int(points),1000)), "action": {"type": str(action)}}
                if action in {"timeout","tempban"}:
                    item["action"]["duration_minutes"] = max(1,min(int(duration or 10),525600 if action == "tempban" else 40320))
                thresholds.append(item)
            settings["point_thresholds"] = sorted(thresholds,key=lambda item:item["points"])
        if section == "moderation_logs":
            log_id = int(form["log_channel_id"]) if form.get("log_channel_id") else None
            if log_id and log_id not in {int(item["id"]) for item in channels if int(item["type"]) == 0}:
                raise ValueError("invalid log channel")
            settings["log_channel_id"] = log_id
            for name in ("message_delete","message_edit","warning","timeout","kick","ban","unban","join","leave","automod","anti_spam","anti_raid","admin"):
                settings[f"log_{name}"] = form.get(f"log_{name}") == "on"
    except (TypeError, ValueError):
        return RedirectResponse(f"{target}?error=invalid", status_code=303)
    storage.set_module(guild_id, section, enabled=form.get("enabled") == "on", settings=settings)
    return RedirectResponse(f"{target}?saved=1", status_code=303)


@app.post("/servers/{guild_id}/moderation/{family}/rules")
async def save_moderation_rule_v2(request: Request, guild_id: int, family: str):
    if family not in FAMILY_TRIGGERS:
        raise HTTPException(status_code=404)
    form = await request.form()
    target = f"/servers/{guild_id}/moderation/{family}"
    if not _csrf_ok(request, form.get("csrf_token")):
        return RedirectResponse(f"{target}?error=csrf", status_code=303)
    await authorized(request, guild_id, live=True)
    channels, roles, bot_permissions = await api.guild_resources(guild_id, use_cache=False)
    try:
        channel_ids, text_ids = {int(item["id"]) for item in channels}, {int(item["id"]) for item in channels if int(item["type"]) == 0}
        rule = _typed_moderation_rule(form, family, channel_ids, {int(item["id"]) for item in roles})
        _rule_resource_permissions(rule, channel_ids, text_ids, {int(item["id"]) for item in roles}, bot_permissions)
        rule_id = int(form["rule_id"]) if form.get("rule_id") else None
        storage.save_moderation_rule(guild_id, rule, rule_id)
    except (KeyError,TypeError,ValueError,PermissionError):
        return RedirectResponse(f"{target}?error=invalid-rule", status_code=303)
    return RedirectResponse(f"{target}?saved=rule", status_code=303)


@app.get("/servers/{guild_id}/moderation/{family}/rules/{rule_id}.json")
async def moderation_rule_json(request: Request, guild_id: int, family: str, rule_id: int):
    if family not in FAMILY_TRIGGERS:
        raise HTTPException(status_code=404)
    await authorized(request, guild_id)
    rule = storage.moderation_rule(guild_id, rule_id)
    if not rule or rule["family"] != family:
        raise HTTPException(status_code=404)
    return JSONResponse(rule)


@app.post("/servers/{guild_id}/moderation/{family}/rules/{rule_id}/delete")
async def delete_moderation_rule_v2(request: Request, guild_id: int, family: str, rule_id: int):
    form = await request.form()
    target = f"/servers/{guild_id}/moderation/{family}"
    if not _csrf_ok(request, form.get("csrf_token")):
        return RedirectResponse(f"{target}?error=csrf", status_code=303)
    await authorized(request, guild_id, live=True)
    rule = storage.moderation_rule(guild_id, rule_id)
    if not rule or rule["family"] != family:
        raise HTTPException(status_code=404)
    storage.delete_moderation_rule(guild_id, rule_id)
    return RedirectResponse(f"{target}?saved=deleted", status_code=303)


@app.post("/servers/{guild_id}/moderation/{family}/rules/{rule_id}/duplicate")
async def duplicate_moderation_rule_v2(request: Request, guild_id: int, family: str, rule_id: int):
    if family not in FAMILY_TRIGGERS:
        raise HTTPException(status_code=404)
    form = await request.form()
    target = f"/servers/{guild_id}/moderation/{family}"
    if not _csrf_ok(request, form.get("csrf_token")):
        return RedirectResponse(f"{target}?error=csrf", status_code=303)
    await authorized(request, guild_id, live=True)
    rule = storage.moderation_rule(guild_id, rule_id)
    if not rule or rule["family"] != family:
        raise HTTPException(status_code=404)
    copy = {key: value for key, value in rule.items() if key not in {"id", "guild_id", "revision", "created_at", "updated_at", "legacy_rule_id"}}
    copy["name"] = f"{rule['name']} (コピー)"[:100]
    copy["enabled"] = False
    storage.save_moderation_rule(guild_id, validate_rule(copy))
    return RedirectResponse(f"{target}?saved=duplicated", status_code=303)


@app.post("/servers/{guild_id}/moderation/{family}/preview")
async def preview_moderation_rule(request: Request, guild_id: int, family: str):
    if family not in FAMILY_TRIGGERS:
        raise HTTPException(status_code=404)
    form = await request.form()
    target = f"/servers/{guild_id}/moderation/{family}"
    if not _csrf_ok(request, form.get("csrf_token")):
        return RedirectResponse(f"{target}?error=csrf",status_code=303)
    await authorized(request,guild_id)
    channels,roles,_ = await api.guild_resources(guild_id)
    try:
        rule = _typed_moderation_rule(form,family,{int(item["id"]) for item in channels},{int(item["id"]) for item in roles})
        context = MessageContext(guild_id,1,int(form.get("preview_channel_id") or 1),content=str(form.get("preview_content", ""))[:4000],
            mention_count=max(0,min(int(form.get("preview_mentions",0)),100)),attachment_count=max(0,min(int(form.get("preview_attachments",0)),20)),
            sticker_count=max(0,min(int(form.get("preview_stickers",0)),100)),event_type=rule["event_type"])
        engine = AutoModEngine()
        matches = []
        repeats = int(rule["trigger_config"].get("limit",1)) if rule["trigger_type"] in {"message_rate","duplicate","mention_rate","link_rate","attachment_rate","reaction_rate","reaction_burst","join_rate","leave_rate","new_account_ratio","emoji_sticker_rate"} else 1
        for _ in range(max(1,min(repeats,100))):
            matches = await engine.evaluate(context,[{**rule,"id":1}])
        result = {"matched":bool(matches),"reason":matches[0].reason if matches else "一致しませんでした"}
    except (TypeError,ValueError):
        result = {"matched":False,"reason":"ルールまたはテスト入力が無効です"}
    request.session[f"moderation_preview:{guild_id}:{family}"] = result
    return RedirectResponse(f"{target}?preview={'matched' if result['matched'] else 'clear'}&preview_reason={quote_plus(result['reason'])}",status_code=303)


@app.post("/servers/{guild_id}/moderation/actions")
async def request_moderation_action(request: Request, guild_id: int):
    form = await request.form()
    target = f"/servers/{guild_id}/moderation/moderation_actions"
    if not _csrf_ok(request, form.get("csrf_token")):
        return RedirectResponse(f"{target}?error=csrf", status_code=303)
    token = await authorized(request, guild_id, live=True)
    user = await api.current_user(token, use_cache=False)
    if not storage.module_enabled(guild_id, "moderation"):
        return RedirectResponse(f"{target}?error=moderation-disabled", status_code=303)
    action = str(form.get("action", ""))
    if action not in {"warn","timeout","untimeout","kick","ban","unban","softban","purge","lock","unlock","lockdown","unlockdown"} or form.get("confirm") != "confirm":
        return RedirectResponse(f"{target}?error=confirmation", status_code=303)
    try:
        target_id = int(form["target_user_id"]) if form.get("target_user_id") else None
        channel_id = int(form["channel_id"]) if form.get("channel_id") else None
        duration = max(1,min(int(form.get("duration_minutes",10)),525600))
        count = max(1,min(int(form.get("count",10)),100))
        reason = str(form.get("reason", "")).strip()[:500]
        channels, _, bot_permissions = await api.guild_resources(guild_id, use_cache=False)
        guild_channel_ids = {int(item["id"]) for item in channels}
        text_channel_ids = {int(item["id"]) for item in channels if int(item["type"]) in {0, 5, 15}}
        target_actions = {"warn", "timeout", "untimeout", "kick", "ban", "unban", "softban"}
        channel_actions = {"purge", "lock", "unlock"}
        required_permissions = {
            "timeout": "moderate_members", "untimeout": "moderate_members", "kick": "kick_members",
            "ban": "ban_members", "unban": "ban_members", "softban": "ban_members",
            "purge": "manage_messages", "lock": "manage_channels", "unlock": "manage_channels",
            "lockdown": "manage_channels", "unlockdown": "manage_channels",
        }
        if action in target_actions and (target_id is None or target_id <= 0):
            raise ValueError("target user is required")
        if action in channel_actions and (channel_id is None or channel_id not in text_channel_ids):
            raise ValueError("a channel from this server is required")
        if channel_id is not None and channel_id not in guild_channel_ids:
            raise ValueError("channel belongs to another server")
        if not reason:
            raise ValueError("reason is required")
        permission = required_permissions.get(action)
        if permission and not (bot_permissions & PERMISSION_BITS[permission]):
            raise PermissionError(f"missing {permission}")
    except (TypeError, ValueError, PermissionError):
        return RedirectResponse(f"{target}?error=invalid", status_code=303)
    nonce = secrets.token_urlsafe(16)
    storage.enqueue_moderation_action(guild_id,int(user["id"]),action,target_user_id=target_id,channel_id=channel_id,
        reason=reason,options={"duration_minutes":duration,"count":count},dedupe_key=f"dashboard:{guild_id}:{nonce}")
    return RedirectResponse(f"{target}?saved=queued", status_code=303)


@app.post("/servers/{guild_id}/moderation/infractions/adjust")
async def adjust_infraction(request: Request, guild_id: int):
    form = await request.form()
    target = f"/servers/{guild_id}/moderation/infractions"
    if not _csrf_ok(request, form.get("csrf_token")):
        return RedirectResponse(f"{target}?error=csrf", status_code=303)
    token = await authorized(request, guild_id, live=True)
    user = await api.current_user(token, use_cache=False)
    try:
        user_id = int(form["target_user_id"])
        operation = str(form.get("operation", ""))
        reason = str(form.get("reason", ""))[:500]
        if user_id <= 0 or operation not in {"add", "revoke", "note"} or not reason:
            raise ValueError("invalid infraction operation")
        if operation == "add":
            points = max(1,min(int(form.get("points",1)),1000))
            expires_days = max(0,min(int(form.get("expires_days",30)),3650))
            storage.enqueue_moderation_action(guild_id,int(user["id"]),"points",target_user_id=user_id,reason=reason,
                options={"points":points,"expires_days":expires_days},dedupe_key=f"infraction:{guild_id}:{secrets.token_urlsafe(16)}")
        elif operation == "revoke":
            revoked = storage.clear_warnings(guild_id,user_id)
            storage.add_case(guild_id,user_id,"revoke_points",f"{reason} ({revoked}件)",int(user["id"]),source="manual")
        else:
            storage.add_case(guild_id,user_id,"note",reason,int(user["id"]),source="manual")
    except (KeyError,TypeError,ValueError):
        return RedirectResponse(f"{target}?error=invalid",status_code=303)
    return RedirectResponse(f"{target}?user_id={user_id}&saved=1",status_code=303)


def _rule_resource_permissions(rule: dict, channel_ids: set[int], text_channel_ids: set[int], role_ids: set[int], bot_permissions: int) -> None:
    channel_values = set(rule["conditions"].get("channel_ids", [])) | set(rule["conditions"].get("category_ids", [])) | set(rule["exemptions"].get("channel_ids", []))
    channel_values |= set(rule["trigger_config"].get("channel_ids", []))
    role_values = set(rule["conditions"].get("required_role_ids", [])) | set(rule["conditions"].get("excluded_role_ids", [])) | set(rule["exemptions"].get("role_ids", []))
    for action in rule["actions"]:
        if action.get("channel_id"):
            channel_values.add(int(action["channel_id"]))
            if int(action["channel_id"]) not in text_channel_ids:
                raise ValueError("Notification target must be a text channel")
    if channel_values - channel_ids or role_values - role_ids:
        raise ValueError("Rule contains a resource from another server")
    required = set()
    for action in rule["actions"]:
        required |= {"delete": {"manage_messages"}, "purge": {"manage_messages"}, "remove_reaction": {"manage_messages"},
                     "notify": {"send_messages"}, "log": {"send_messages"}, "timeout": {"moderate_members"}, "untimeout": {"moderate_members"},
                     "kick": {"kick_members"}, "ban": {"ban_members"}, "unban": {"ban_members"}, "tempban": {"ban_members"},
                     "softban": {"ban_members"}, "lock": {"manage_channels"}, "unlock": {"manage_channels"},
                     "lockdown": {"manage_channels"}, "unlockdown": {"manage_channels"}}.get(action["type"], set())
    if not bot_permissions & ADMINISTRATOR and any(not bot_permissions & PERMISSION_BITS[item] for item in required):
        raise PermissionError("Bot is missing an action permission")


@app.post("/servers/{guild_id}/automod/settings")
async def save_automod_settings(request: Request, guild_id: int):
    target = f"/servers/{guild_id}/modules/automod"
    form = await request.form()
    if not _csrf_ok(request, form.get("csrf_token")):
        return RedirectResponse(f"{target}?error=csrf", status_code=303)
    await authorized(request, guild_id, live=True)
    channels, roles, bot_permissions = await api.guild_resources(guild_id, use_cache=False)
    channel_ids, text_channel_ids = {int(item["id"]) for item in channels}, {int(item["id"]) for item in channels if int(item["type"]) == 0}
    role_ids = {int(item["id"]) for item in roles}
    try:
        log_channel = int(form["log_channel_id"]) if form.get("log_channel_id") else None
        if log_channel is not None and log_channel not in text_channel_ids:
            raise ValueError("invalid log channel")
        user_text = str(form.get("immune_user_ids", "")).replace(",", "\n")
        immune_users = list(dict.fromkeys(int(value.strip()) for value in user_text.splitlines() if value.strip()))
        if len(immune_users) > 100 or any(value <= 0 for value in immune_users):
            raise ValueError("invalid immune user")
        retention = max(1, min(int(form.get("evidence_retention_days", 30)), 365))
        thresholds = _json_object(form.get("point_thresholds"), [])
        normalized_thresholds = []
        for item in thresholds[:20]:
            points, action = int(item["points"]), dict(item["action"])
            if not 1 <= points <= 1000 or action.get("type") not in {"timeout", "kick", "ban", "tempban"}:
                raise ValueError("invalid threshold")
            if action["type"] in {"timeout", "tempban"}:
                action["duration_minutes"] = max(1, min(int(action.get("duration_minutes", 60)), 525600 if action["type"] == "tempban" else 40320))
            normalized_thresholds.append({"points": points, "action": action})
        normalized_thresholds.sort(key=lambda item: item["points"])
        threshold_permissions = {"timeout": "moderate_members", "kick": "kick_members", "ban": "ban_members", "tempban": "ban_members"}
        if not bot_permissions & ADMINISTRATOR and any(not bot_permissions & PERMISSION_BITS[threshold_permissions[item["action"]["type"]]] for item in normalized_thresholds):
            raise PermissionError("missing threshold permission")
        values = {
            "log_channel_id": log_channel,
            "immune_role_ids": _form_ids(form.getlist("immune_role_ids"), role_ids),
            "immune_user_ids": immune_users,
            "immune_channel_ids": _form_ids(form.getlist("immune_channel_ids"), channel_ids),
            "evidence_excluded_channel_ids": _form_ids(form.getlist("evidence_excluded_channel_ids"), channel_ids),
            "evidence_retention_days": retention,
            "point_thresholds": normalized_thresholds,
        }
        if not bot_permissions & ADMINISTRATOR and not bot_permissions & PERMISSION_BITS["manage_messages"]:
            raise PermissionError("missing permission")
    except (KeyError, TypeError, ValueError, PermissionError, json.JSONDecodeError):
        return RedirectResponse(f"{target}?error=invalid-selection", status_code=303)
    current = storage.get_module(guild_id, "automod")
    current["settings"].update(values)
    storage.set_module(guild_id, "automod", enabled=form.get("enabled") == "on", settings=current["settings"])
    return RedirectResponse(f"{target}?saved=1", status_code=303)


def _rule_from_form(form: Any) -> dict:
    return validate_rule({
        "name": str(form.get("name", "")), "enabled": form.get("enabled") == "on", "mode": str(form.get("mode", "monitor")),
        "priority": form.get("priority", 100), "stop_on_match": form.get("stop_on_match") == "on",
        "trigger_type": str(form.get("trigger_type", "")),
        "trigger_config": _json_object(form.get("trigger_config"), {}),
        "conditions": _json_object(form.get("conditions"), {}),
        "exemptions": _json_object(form.get("exemptions"), {}),
        "actions": _json_object(form.get("actions"), []),
    })


@app.post("/servers/{guild_id}/automod/rules")
async def save_automod_rule(request: Request, guild_id: int):
    target = f"/servers/{guild_id}/modules/automod"
    form = await request.form()
    if not _csrf_ok(request, form.get("csrf_token")):
        return RedirectResponse(f"{target}?error=csrf", status_code=303)
    await authorized(request, guild_id, live=True)
    channels, roles, bot_permissions = await api.guild_resources(guild_id, use_cache=False)
    try:
        rule = _rule_from_form(form)
        _rule_resource_permissions(rule, {int(item["id"]) for item in channels},
            {int(item["id"]) for item in channels if int(item["type"]) == 0},
            {int(item["id"]) for item in roles}, bot_permissions)
        rule_id = int(form["rule_id"]) if form.get("rule_id") else None
        storage.save_automod_rule(guild_id, rule, rule_id)
    except (KeyError, TypeError, ValueError, PermissionError, json.JSONDecodeError):
        return RedirectResponse(f"{target}?error=invalid-rule", status_code=303)
    return RedirectResponse(f"{target}?saved=rule", status_code=303)


@app.post("/servers/{guild_id}/automod/rules/{rule_id}/duplicate")
async def duplicate_automod_rule(request: Request, guild_id: int, rule_id: int):
    form = await request.form()
    target = f"/servers/{guild_id}/modules/automod"
    if not _csrf_ok(request, form.get("csrf_token")):
        return RedirectResponse(f"{target}?error=csrf", status_code=303)
    await authorized(request, guild_id, live=True)
    rule = storage.automod_rule(guild_id, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="ルールが見つかりません")
    rule["name"] = f"{rule['name']} のコピー"[:100]
    storage.save_automod_rule(guild_id, validate_rule(rule))
    return RedirectResponse(f"{target}?saved=rule", status_code=303)


@app.post("/servers/{guild_id}/automod/rules/{rule_id}/delete")
async def delete_automod_rule(request: Request, guild_id: int, rule_id: int):
    form = await request.form()
    target = f"/servers/{guild_id}/modules/automod"
    if not _csrf_ok(request, form.get("csrf_token")):
        return RedirectResponse(f"{target}?error=csrf", status_code=303)
    await authorized(request, guild_id, live=True)
    if not storage.delete_automod_rule(guild_id, rule_id):
        raise HTTPException(status_code=404, detail="ルールが見つかりません")
    return RedirectResponse(f"{target}?saved=deleted", status_code=303)


@app.post("/servers/{guild_id}/automod/preview")
async def preview_automod_rule(request: Request, guild_id: int):
    form = await request.form()
    target = f"/servers/{guild_id}/modules/automod"
    if not _csrf_ok(request, form.get("csrf_token")):
        return RedirectResponse(f"{target}?error=csrf", status_code=303)
    await authorized(request, guild_id)
    try:
        rule = _rule_from_form(form)
        engine = AutoModEngine()
        context = MessageContext(guild_id=guild_id, user_id=1, channel_id=int(form.get("preview_channel_id") or 1),
            content=str(form.get("preview_content", ""))[:4000], mention_count=max(0, min(int(form.get("preview_mentions", 0)), 100)),
            attachment_count=max(0, min(int(form.get("preview_attachments", 0)), 20)))
        matches = []
        repeats = int(rule.get("trigger_config", {}).get("limit", 1)) if rule["trigger_type"] in {"message_rate", "duplicate", "mention_rate", "link_rate", "attachment_rate"} else 1
        for _ in range(repeats):
            matches = await engine.evaluate(context, [{**rule, "id": 1}])
        result = {"matched": bool(matches), "reason": matches[0].reason if matches else "一致しませんでした", "actions": rule["actions"]}
    except (TypeError, ValueError, json.JSONDecodeError):
        result = {"matched": False, "reason": "ルールまたはテスト入力が無効です", "actions": []}
    request.session[f"automod_preview:{guild_id}"] = result
    return RedirectResponse(target, status_code=303)


@app.post("/servers/{guild_id}/social/subscriptions")
async def save_social_subscription(request: Request, guild_id: int):
    module_id = request.query_params.get("module_id", "")
    provider_for_module = SOCIAL_MODULE_PROVIDERS.get(module_id)
    target = f"/servers/{guild_id}/modules/{module_id}" if provider_for_module else f"/servers/{guild_id}"
    form = await request.form()
    if not secrets.compare_digest(str(form.get("csrf_token", "")), request.session.get("csrf_token", "")):
        return RedirectResponse(f"{target}?error=csrf", status_code=303)
    await authorized(request, guild_id, live=True)
    channels, roles, _ = await api.guild_resources(guild_id, use_cache=False)
    channel_ids = {int(item["id"]) for item in channels if int(item["type"]) == 0}
    role_ids = {int(item["id"]) for item in roles}
    provider = str(form.get("provider", ""))
    account_id, account_name = str(form.get("account_id", "")).strip()[:160], str(form.get("account_name", "")).strip()[:160]
    template = str(form.get("template", ""))[:1000]
    events = [str(value) for value in form.getlist("events") if value]
    try:
        channel_id = int(str(form.get("channel_id", "")))
        role_raw = str(form.get("role_id", ""))
        role_id = int(role_raw) if role_raw else None
    except ValueError:
        return RedirectResponse(f"{target}?error=invalid-selection", status_code=303)
    allowed_events = {"youtube": {"video", "live_start"}, "twitch": {"live"}, "tiktok": {"post"}, "x": {"post"}, "instagram": {"post", "reel"}}
    oauth_providers = {"tiktok", "instagram"}
    if provider != provider_for_module or provider not in allowed_events or not social_provider_available(provider) or not account_id or not account_name or channel_id not in channel_ids or (role_id is not None and role_id not in role_ids) or not events or not set(events).issubset(allowed_events[provider]) or (provider in oauth_providers and not storage.social_connection(guild_id, provider, account_id)):
        return RedirectResponse(f"{target}?error=invalid-selection", status_code=303)
    if provider == "youtube" and not await subscribe_youtube_websub(account_id):
        return RedirectResponse(f"{target}?error=social-provider-unavailable", status_code=303)
    try:
        storage.save_social_subscription(guild_id, provider, account_id, account_name, channel_id, role_id, template, events)
    except ValueError:
        return RedirectResponse(f"{target}?error=social-limit", status_code=303)
    storage.set_module(guild_id, module_id, enabled=True)
    return RedirectResponse(f"{target}?saved=1", status_code=303)


@app.post("/servers/{guild_id}/social/subscriptions/{subscription_id}/delete")
async def delete_social_subscription(request: Request, guild_id: int, subscription_id: int):
    module_id = request.query_params.get("module_id", "")
    provider_for_module = SOCIAL_MODULE_PROVIDERS.get(module_id)
    target = f"/servers/{guild_id}/modules/{module_id}" if provider_for_module else f"/servers/{guild_id}"
    form = await request.form()
    if not secrets.compare_digest(str(form.get("csrf_token", "")), request.session.get("csrf_token", "")):
        return RedirectResponse(f"{target}?error=csrf", status_code=303)
    await authorized(request, guild_id, live=True)
    subscription = storage.social_subscription(subscription_id)
    if not provider_for_module or not subscription or subscription["guild_id"] != guild_id or subscription["provider"] != provider_for_module:
        return RedirectResponse(f"{target}?error=invalid-selection", status_code=303)
    storage.delete_social_subscription(guild_id, subscription_id)
    storage.set_module(guild_id, module_id, enabled=bool(storage.social_subscriptions(guild_id, provider_for_module)))
    return RedirectResponse(f"{target}?saved=1", status_code=303)


@app.post("/servers/{guild_id}/social/connect/{provider}")
async def begin_social_connection(request: Request, guild_id: int, provider: str):
    form = await request.form()
    target = f"/servers/{guild_id}/modules/{provider}_updates" if provider in {"tiktok", "instagram"} else f"/servers/{guild_id}"
    if not secrets.compare_digest(str(form.get("csrf_token", "")), request.session.get("csrf_token", "")):
        return RedirectResponse(f"{target}?error=csrf", status_code=303)
    await authorized(request, guild_id, live=True)
    if not social_cipher.available:
        return RedirectResponse(f"{target}?error=social-token-key", status_code=303)
    state = secrets.token_urlsafe(32)
    if provider == "tiktok" and settings.tiktok_client_key and settings.tiktok_redirect_uri:
        storage.create_social_oauth_state(state, guild_id, provider)
        params = urlencode({"client_key": settings.tiktok_client_key, "response_type": "code", "scope": "user.info.basic,video.list", "redirect_uri": settings.tiktok_redirect_uri, "state": state})
        return RedirectResponse(f"https://www.tiktok.com/v2/auth/authorize/?{params}", status_code=303)
    if provider == "instagram" and settings.instagram_app_id and settings.instagram_redirect_uri:
        storage.create_social_oauth_state(state, guild_id, provider)
        params = urlencode({"client_id": settings.instagram_app_id, "redirect_uri": settings.instagram_redirect_uri, "response_type": "code", "scope": "instagram_business_basic", "state": state})
        return RedirectResponse(f"https://www.instagram.com/oauth/authorize?{params}", status_code=303)
    return RedirectResponse(f"{target}?error=social-provider-unavailable", status_code=303)


@app.get("/social/oauth/{provider}/callback")
async def social_oauth_callback(provider: str, code: str | None = None, state: str | None = None, error: str | None = None):
    if not state or error:
        raise HTTPException(status_code=400, detail="ソーシャルOAuth認証が拒否されました")
    guild_id = storage.consume_social_oauth_state(state, provider)
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
    storage.save_social_connection(guild_id, provider, str(account_id), str(account_name), social_cipher.encrypt(str(token)), social_cipher.encrypt(str(payload["refresh_token"])) if payload.get("refresh_token") else None, int(time.time()) + int(payload.get("expires_in", 0)) if payload.get("expires_in") else None)
    return RedirectResponse(f"/servers/{guild_id}/modules/{provider}_updates?saved=connected", status_code=303)


@app.get("/favicon.ico")
async def favicon():
    return RedirectResponse(avatar_url(await api.bot_user()), status_code=307)


@app.get("/webhooks/youtube")
async def youtube_webhook_verify(request: Request):
    """WebSub lease validation; the public callback URL is configured at YouTube."""
    return PlainTextResponse(request.query_params.get("hub.challenge", ""))


@app.post("/webhooks/youtube")
async def youtube_webhook(request: Request):
    body = await request.body()
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
    storage.enqueue_social_event("youtube", f"youtube:video:{video_id}", account_id, {"account": account_id, "title": title, "url": f"https://www.youtube.com/watch?v={video_id}", "platform": "YouTube", "type": "video"})
    return PlainTextResponse("ok")


def optional_id(value: str) -> int | None:
    return int(value) if value else None


@app.post("/servers/{guild_id}/modules/{module_id}")
async def save_module_settings(request: Request, guild_id: int, module_id: str):
    if module_id in {"chat_filter", "anti_spam"}:
        return RedirectResponse(f"/servers/{guild_id}/modules/automod", status_code=303)
    target = f"/servers/{guild_id}/modules/{module_id}"
    form = await request.form()
    csrf_token = str(form.get("csrf_token", ""))
    enabled = form.get("enabled") == "on"
    if not secrets.compare_digest(csrf_token, request.session.get("csrf_token", "")):
        return RedirectResponse(f"{target}?error=csrf", status_code=303)
    await authorized(request, guild_id, live=True)
    try:
        feature = get_feature(module_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="機能が見つかりません")
    channels, roles, bot_permissions = await api.guild_resources(guild_id, use_cache=False)
    channel_ids, role_ids = {int(item["id"]) for item in channels}, {int(item["id"]) for item in roles}
    channel_types = {int(item["id"]): int(item["type"]) for item in channels}
    try:
        management = optional_id(str(form.get("management_channel_id", "")))
        welcome = optional_id(str(form.get("welcome_channel_id", "")))
        leave = optional_id(str(form.get("leave_channel_id", "")))
        role = optional_id(str(form.get("default_role_id", "")))
        reaction_channel = optional_id(str(form.get("reaction_role_channel_id", "")))
        reaction_roles = [int(value) for value in form.getlist("reaction_role_ids") if value]
        stats_channel = optional_id(str(form.get("stats_channel_id", "")))
        temp_trigger = optional_id(str(form.get("temp_voice_trigger_id", "")))
        temp_category = optional_id(str(form.get("temp_voice_category_id", "")))
        ticket_panel_channel = optional_id(str(form.get("ticket_panel_channel_id", "")))
        ticket_category = optional_id(str(form.get("ticket_category_id", "")))
        ticket_staff_role = optional_id(str(form.get("ticket_staff_role_id", "")))
        ticket_log_channel = optional_id(str(form.get("ticket_log_channel_id", "")))
        text_notification_channel = optional_id(str(form.get("text_notification_channel_id", "")))
        voice_notification_channel = optional_id(str(form.get("voice_notification_channel_id", "")))
    except ValueError:
        return RedirectResponse(f"{target}?error=invalid-selection", status_code=303)
    if len(reaction_roles) > 25 or len(set(reaction_roles)) != len(reaction_roles) or (management is not None and channel_types.get(management) != 0) or (welcome is not None and channel_types.get(welcome) != 0) or (leave is not None and channel_types.get(leave) != 0) or (role is not None and role not in role_ids) or (reaction_channel is not None and channel_types.get(reaction_channel) != 0) or any(value not in role_ids for value in reaction_roles) or (stats_channel is not None and channel_types.get(stats_channel) != 2) or (temp_trigger is not None and channel_types.get(temp_trigger) != 2) or (temp_category is not None and channel_types.get(temp_category) != 4) or (ticket_panel_channel is not None and channel_types.get(ticket_panel_channel) != 0) or (ticket_category is not None and channel_types.get(ticket_category) != 4) or (ticket_staff_role is not None and ticket_staff_role not in role_ids) or (ticket_log_channel is not None and channel_types.get(ticket_log_channel) != 0) or (text_notification_channel is not None and channel_types.get(text_notification_channel) != 0) or (voice_notification_channel is not None and channel_types.get(voice_notification_channel) != 0):
        return RedirectResponse(f"{target}?error=invalid-selection", status_code=303)
    def bounded_int(name: str, default: int, low: int, high: int) -> int:
        try:
            return max(low, min(int(str(form.get(name, default))), high))
        except ValueError:
            raise ValueError(name)
    def parse_rewards(prefix: str) -> list[dict[str, int]]:
        levels, roles_for_levels = form.getlist(f"{prefix}_reward_level"), form.getlist(f"{prefix}_reward_role_id")
        if len(levels) != len(roles_for_levels) or len(levels) > 25:
            raise ValueError(prefix)
        rewards = []
        for level, reward_role_id in zip(levels, roles_for_levels):
            parsed_level, parsed_role = int(level), int(reward_role_id)
            if not 1 <= parsed_level <= 100000 or parsed_role not in role_ids:
                raise ValueError(prefix)
            rewards.append({"level": parsed_level, "role_id": parsed_role})
        if len({reward["level"] for reward in rewards}) != len(rewards):
            raise ValueError(prefix)
        return sorted(rewards, key=lambda reward: reward["level"])
    try:
        values = {
            "management_channel_id": management, "welcome_channel_id": welcome, "default_role_id": role,
            "log_message": form.get("log_message") == "on",
            "log_voice": form.get("log_voice") == "on",
            "log_channel": form.get("log_channel") == "on",
            "log_member": form.get("log_member") == "on",
            "log_role": form.get("log_role") == "on",
            "log_server": form.get("log_server") == "on",
            "welcome_enabled": form.get("welcome_enabled") == "on",
            "welcome_format": str(form.get("welcome_format", "text")),
            "welcome_content": str(form.get("welcome_content", ""))[:4096],
            "leave_enabled": form.get("leave_enabled") == "on",
            "leave_channel_id": leave,
            "leave_format": str(form.get("leave_format", "text")),
            "leave_content": str(form.get("leave_content", ""))[:4096],
            "escalation_enabled": form.get("escalation_enabled") == "on",
            "escalation_threshold": bounded_int("escalation_threshold", 3, 1, 100),
            "escalation_action": str(form.get("escalation_action", "timeout")),
            "escalation_timeout_minutes": bounded_int("escalation_timeout_minutes", 60, 1, 28 * 24 * 60),
            "dm_notify": form.get("dm_notify") == "on",
            "filter_keywords": str(form.get("filter_keywords", ""))[:4000],
            "filter_regex": str(form.get("filter_regex", ""))[:4000],
            "filter_action": "delete_warn" if form.get("filter_action") == "delete_warn" else "delete",
            "safe_browsing_enabled": form.get("safe_browsing_enabled") == "on",
            "spam_window_seconds": bounded_int("spam_window_seconds", 10, 1, 300),
            "spam_message_limit": bounded_int("spam_message_limit", 6, 2, 50),
            "spam_mention_limit": bounded_int("spam_mention_limit", 10, 1, 100),
            "spam_duplicate_limit": bounded_int("spam_duplicate_limit", 3, 2, 20),
            "spam_action": "timeout" if form.get("spam_action") == "timeout" else "delete",
            "spam_timeout_minutes": bounded_int("spam_timeout_minutes", 10, 1, 28 * 24 * 60),
            "reaction_role_channel_id": reaction_channel,
            "reaction_role_ids": reaction_roles,
            "reaction_role_title": str(form.get("reaction_role_title", ""))[:256],
            "reaction_role_description": str(form.get("reaction_role_description", ""))[:4000],
            "stats_channel_id": stats_channel,
            "stats_template": str(form.get("stats_template", "Members: {members} | Bots: {bots} | Roles: {roles}"))[:90],
            "temp_voice_trigger_id": temp_trigger,
            "temp_voice_category_id": temp_category,
            "temp_voice_name": str(form.get("temp_voice_name", "{member}'s room"))[:100],
            "ticket_panel_channel_id": ticket_panel_channel,
            "ticket_category_id": ticket_category,
            "ticket_staff_role_id": ticket_staff_role,
            "ticket_log_channel_id": ticket_log_channel,
            "ticket_panel_title": str(form.get("ticket_panel_title", ""))[:256],
            "ticket_panel_description": str(form.get("ticket_panel_description", ""))[:4000],
            "trust_retention_days": bounded_int("trust_retention_days", 90, 1, 3650),
            "trust_flag_threshold": bounded_int("trust_flag_threshold", 60, 0, 100),
            "text_notification_channel_id": text_notification_channel,
            "text_role_rewards": parse_rewards("text"),
            "voice_enabled": form.get("voice_enabled") == "on",
            "voice_notification_channel_id": voice_notification_channel,
            "voice_role_rewards": parse_rewards("voice"),
            "voice_xp_per_minute": bounded_int("voice_xp_per_minute", 5, 1, 100),
            "voice_allow_solo": form.get("voice_allow_solo") == "on",
            "voice_allow_muted": form.get("voice_allow_muted") == "on",
        }
    except ValueError:
        return RedirectResponse(f"{target}?error=invalid-selection", status_code=303)
    if values["escalation_action"] not in {"timeout", "kick", "ban"}:
        return RedirectResponse(f"{target}?error=invalid-selection", status_code=303)
    if values["welcome_format"] not in {"text", "embed"} or values["leave_format"] not in {"text", "embed"}:
        return RedirectResponse(f"{target}?error=invalid-selection", status_code=303)
    if module_id == "welcome":
        enabled = values["welcome_enabled"] or values["leave_enabled"]
        invalid_welcome = values["welcome_enabled"] and (welcome is None or not values["welcome_content"].strip() or (values["welcome_format"] == "text" and len(values["welcome_content"]) > 2000))
        invalid_leave = values["leave_enabled"] and (leave is None or not values["leave_content"].strip() or (values["leave_format"] == "text" and len(values["leave_content"]) > 2000))
        if invalid_welcome or invalid_leave:
            draft_key = f"{guild_id}:{module_id}"
            drafts = request.session.get("module_drafts", {})
            drafts[draft_key] = {"enabled": enabled, "settings": {field: values[field] for field in feature.fields}}
            request.session["module_drafts"] = drafts
            return RedirectResponse(f"{target}?error=setup-required", status_code=303)
    if module_id == "audit_log":
        enabled = any(values[key] for key in ("log_message", "log_voice", "log_channel", "log_member", "log_role", "log_server"))
        draft_key = f"{guild_id}:{module_id}"
        drafts = request.session.get("module_drafts", {})
        if enabled and management is None:
            drafts[draft_key] = {"enabled": enabled, "settings": {field: values[field] for field in feature.fields}}
            request.session["module_drafts"] = drafts
            return RedirectResponse(f"{target}?error=setup-required", status_code=303)
        if values["log_member"] and not (bot_permissions & ADMINISTRATOR or bot_permissions & PERMISSION_BITS["view_audit_log"]):
            drafts[draft_key] = {"enabled": enabled, "settings": {field: values[field] for field in feature.fields}}
            request.session["module_drafts"] = drafts
            return RedirectResponse(f"{target}?error=missing-permissions", status_code=303)
    if module_id == "leveling" and values["voice_enabled"] and voice_notification_channel is None:
        draft_key = f"{guild_id}:{module_id}"
        drafts = request.session.get("module_drafts", {})
        drafts[draft_key] = {"enabled": enabled, "settings": {field: values[field] for field in feature.fields}}
        request.session["module_drafts"] = drafts
        return RedirectResponse(f"{target}?error=setup-required", status_code=303)
    if module_id == "leveling" and (values["text_role_rewards"] or values["voice_role_rewards"]) and not (bot_permissions & ADMINISTRATOR or bot_permissions & PERMISSION_BITS["manage_roles"]):
        draft_key = f"{guild_id}:{module_id}"
        drafts = request.session.get("module_drafts", {})
        drafts[draft_key] = {"enabled": enabled, "settings": {field: values[field] for field in feature.fields}}
        request.session["module_drafts"] = drafts
        return RedirectResponse(f"{target}?error=missing-permissions", status_code=303)
    draft_key = f"{guild_id}:{module_id}"
    drafts = request.session.get("module_drafts", {})
    drafts[draft_key] = {"enabled": enabled, "settings": {field: values[field] for field in feature.fields}}
    missing_permissions = [] if bot_permissions & ADMINISTRATOR else [permission for permission in feature.required_bot_permissions if not bot_permissions & PERMISSION_BITS[permission]]
    if enabled and missing_permissions:
        request.session["module_drafts"] = drafts
        return RedirectResponse(f"{target}?error=missing-permissions", status_code=303)
    if enabled and any(not values[field] for field in feature.required_fields):
        request.session["module_drafts"] = drafts
        return RedirectResponse(f"{target}?error=setup-required", status_code=303)
    module = storage.get_module(guild_id, module_id)
    for field in feature.fields:
        module["settings"][field] = values[field]
    storage.set_module(guild_id, module_id, enabled=enabled, settings=module["settings"])
    api.invalidate_guild_resources(guild_id)
    if module_id == "reaction_roles" and form.get("publish_reaction_panel") == "on":
        if not enabled:
            request.session["module_drafts"] = drafts
            return RedirectResponse(f"{target}?error=setup-required", status_code=303)
        selected_roles = [role for role in roles if int(role["id"]) in reaction_roles]
        try:
            panel = await api.publish_reaction_role_panel(reaction_channel, selected_roles, values["reaction_role_title"], values["reaction_role_description"])
            storage.save_reaction_role_panel(int(panel["id"]), guild_id, reaction_roles)
        except Exception:
            return RedirectResponse(f"{target}?error=publish-failed", status_code=303)
    # Keep the legacy columns current for safe backward compatibility.
    if module_id == "welcome":
        storage.update_settings(guild_id, welcome_channel_id=module["settings"].get("welcome_channel_id"))
    if module_id == "autorole":
        storage.update_settings(guild_id, default_role_id=module["settings"].get("default_role_id"))
    if module_id == "audit_log":
        storage.update_settings(guild_id, management_channel_id=module["settings"].get("management_channel_id"))
    drafts.pop(draft_key, None)
    request.session["module_drafts"] = drafts
    return RedirectResponse(f"{target}?saved=1", status_code=303)
