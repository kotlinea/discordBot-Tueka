"""Versioned JSON API consumed by the dashboard v2 SPA."""
from __future__ import annotations

import secrets
import sqlite3
import time
import importlib.util
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response

from automod import AutoModEngine, MessageContext, default_rule, validate_rule
from dashboard.discord_api import ADMINISTRATOR, PERMISSION_BITS
from feature_registry import FEATURES, get_feature, japanese_copy
from social_models import PROVIDERS, PROVIDER_EVENTS, TEMPLATE_VARIABLES, default_templates, normalize_account, render_template, validate_subscription
from ticketing import TicketRepository, TicketService, TicketValidationError, TranscriptStorage, validate_form, validate_panel, validate_settings


FAMILY_TRIGGERS = {
    "automod": ("keyword", "regex", "safe_browsing", "phishing_link", "discord_invite", "domain", "caps", "emoji_sticker_rate", "media_only", "honeypot"),
    "anti_spam": ("message_rate", "duplicate", "mention_rate", "link_rate", "attachment_rate", "reaction_rate", "reaction_burst"),
    "anti_raid": ("join_rate", "leave_rate", "new_account_ratio", "new_member_activity"),
}
MODERATION_SECTIONS = ("automod", "anti_spam", "anti_raid", "infractions", "moderation_actions", "moderation_logs")
ALLOWED_ACTIONS = {"warn", "timeout", "untimeout", "kick", "ban", "unban", "softban", "purge", "lock", "unlock", "lockdown", "unlockdown"}


def _resource_kind(key: str) -> tuple[str, bool] | None:
    if key == "temp_voice_trigger_id" or key.endswith(("channel_id", "category_id")):
        return ("channel", False)
    if key.endswith(("channel_ids", "category_ids")):
        return ("channel", True)
    if key.endswith("role_id"):
        return ("role", False)
    if key.endswith("role_ids"):
        return ("role", True)
    return None


def _serialize_resource_ids(settings: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(settings)
    for key, value in settings.items():
        kind = _resource_kind(key)
        if kind is None:
            continue
        if kind[1]:
            serialized[key] = [str(item) for item in value] if value else []
        else:
            serialized[key] = str(value) if value not in (None, "") else None
    return serialized


def _normalize_resource_ids(settings: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(settings)
    for key, value in settings.items():
        kind = _resource_kind(key)
        if kind is None:
            continue
        if kind[1]:
            normalized[key] = [int(item) for item in value] if value else []
        else:
            normalized[key] = int(value) if value not in (None, "") else None
    return normalized


def _serialize_rule_resource_ids(rule: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(rule)
    for section in ("trigger_config", "conditions", "exemptions"):
        serialized[section] = _serialize_resource_ids(dict(rule.get(section) or {}))
    serialized["actions"] = [_serialize_resource_ids(dict(action)) for action in rule.get("actions", [])]
    return serialized


def create_api_router(storage: Any, discord: Any, settings: Any | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    ticket_repository = TicketRepository(settings.database_path) if settings is not None else None
    ticket_transcripts = TranscriptStorage(settings.data_dir / "ticket-transcripts", settings.ticket_encryption_key, s3={
        "endpoint_url": settings.ticket_s3_endpoint_url, "region": settings.ticket_s3_region, "bucket": settings.ticket_s3_bucket,
        "access_key_id": settings.ticket_s3_access_key_id, "secret_access_key": settings.ticket_s3_secret_access_key,
        "prefix": settings.ticket_s3_prefix,
    }) if settings is not None else None
    ticket_service = TicketService(ticket_repository, ticket_transcripts) if ticket_repository and ticket_transcripts else None

    def token(request: Request) -> str:
        session_id = request.session.get("session_id")
        value = storage.dashboard_session_token(session_id) if session_id else None
        if not value:
            raise HTTPException(401, detail={"code": "authentication_required", "message": "ログインが必要です。"})
        return value

    async def manage(request: Request, guild_id: int, *, live: bool = False) -> str:
        value = token(request)
        if not await discord.can_manage(value, guild_id, use_cache=not live):
            raise HTTPException(403, detail={"code": "guild_forbidden", "message": "このサーバーを管理する権限がありません。"})
        return value

    def tickets_available(guild_id: int) -> None:
        if not settings or not settings.tickets_v2 or (settings.tickets_v2_guilds and guild_id not in settings.tickets_v2_guilds) or not ticket_repository or not ticket_service:
            raise HTTPException(404, detail={"code": "tickets_v2_disabled", "message": "Ticket V2はこのサーバーで利用できません。"})

    async def ticket_actor(request: Request, guild_id: int, *, require_manage: bool = False) -> tuple[int, bool]:
        access = token(request)
        user = await discord.current_user(access)
        user_id = int(user["id"])
        administrator = await discord.can_manage(access, guild_id)
        if administrator:
            return user_id, True
        if require_manage:
            raise HTTPException(403, detail={"code": "guild_forbidden", "message": "管理者権限が必要です。"})
        member = await discord.guild_member(guild_id, user_id)
        role_ids = {int(item) for item in (member or {}).get("roles", [])}
        teams = ticket_repository.teams(guild_id) if ticket_repository else []
        if any(user_id in team.get("user_ids", []) or user_id in team.get("admin_user_ids", []) or role_ids.intersection(team.get("role_ids", [])) for team in teams):
            return user_id, False
        raise HTTPException(403, detail={"code": "ticket_staff_forbidden", "message": "Ticket Staff権限がありません。"})

    async def ticket_subject_access(request: Request, guild_id: int, ticket: dict[str, Any], actor_id: int, administrator: bool) -> None:
        if administrator:
            return
        panel = ticket_repository.panel(guild_id, int(ticket["panel_id"])) if ticket_repository else None
        team = ticket_repository.team(guild_id, int(panel["team_id"])) if panel and panel.get("team_id") else None
        member = await discord.guild_member(guild_id, actor_id)
        roles = {int(item) for item in (member or {}).get("roles", [])}
        if not team or not (actor_id in team.get("user_ids", []) or actor_id in team.get("admin_user_ids", []) or roles.intersection(team.get("role_ids", []))):
            raise HTTPException(403, detail={"code": "ticket_team_forbidden", "message": "このTicketを担当するTeamの権限が必要です。"})

    def csrf(request: Request) -> None:
        supplied = request.headers.get("x-csrf-token", "")
        if not secrets.compare_digest(supplied, request.session.get("csrf_token", "")):
            raise HTTPException(403, detail={"code": "csrf_invalid", "message": "画面を再読み込みして、もう一度保存してください。"})

    @router.get("/session")
    async def session(request: Request) -> dict[str, Any]:
        access = token(request)
        user = await discord.current_user(access)
        avatar_hash = user.get("avatar")
        avatar_url = (
            f"https://cdn.discordapp.com/avatars/{user['id']}/{avatar_hash}.webp?size=128"
            if avatar_hash else
            f"https://cdn.discordapp.com/embed/avatars/{(int(user['id']) >> 22) % 6}.png"
        )
        return {
            "user": {"id": str(user["id"]), "name": user.get("global_name") or user["username"], "avatar_url": avatar_url},
            "csrf_token": request.session.get("csrf_token", ""),
            "preferences": storage.dashboard_preferences(int(user["id"])),
        }

    @router.put("/preferences")
    async def save_preferences(request: Request) -> dict[str, Any]:
        csrf(request)
        access = token(request)
        user, body = await discord.current_user(access), await request.json()
        try:
            return storage.set_dashboard_preferences(
                int(user["id"]), locale=str(body.get("locale", "ja")),
                appearance=str(body.get("appearance", "precision")), color_scheme=str(body.get("color_scheme", "system")),
                navigation_collapsed=bool(body.get("navigation_collapsed", False)),
                expected_revision=int(body["revision"]) if body.get("revision") is not None else None,
            )
        except RuntimeError as exc:
            raise HTTPException(409, detail={"code": "revision_conflict", "message": "別の画面で表示設定が更新されました。再読み込みしてください。"}) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, detail={"code": "preferences_invalid", "message": "表示設定を確認してください。"}) from exc

    @router.get("/guilds")
    async def guilds(request: Request) -> dict[str, Any]:
        access = token(request)
        values = await discord.user_guilds(access)
        bot_guilds = await discord.bot_guild_ids()
        user = await discord.current_user(access); user_id = int(user["id"])
        visible = []
        for item in values:
            guild_id = int(item["id"])
            if guild_id not in bot_guilds:
                continue
            administrator = bool(int(item.get("permissions", "0")) & ADMINISTRATOR)
            ticket_staff = False
            if not administrator and settings and settings.tickets_v2 and (not settings.tickets_v2_guilds or guild_id in settings.tickets_v2_guilds) and ticket_repository:
                teams = ticket_repository.teams(guild_id)
                if teams:
                    member = await discord.guild_member(guild_id, user_id)
                    roles = {int(value) for value in (member or {}).get("roles", [])}
                    ticket_staff = any(user_id in team.get("user_ids", []) or user_id in team.get("admin_user_ids", []) or roles.intersection(team.get("role_ids", [])) for team in teams)
            if administrator or ticket_staff:
                visible.append({"id": str(item["id"]), "name": item["name"], "icon": item.get("icon"), "access": "admin" if administrator else "ticket_staff"})
        return {"items": visible}

    async def resources(request: Request, guild_id: int, *, live: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
        await manage(request, guild_id, live=live)
        return await discord.guild_resources(guild_id, use_cache=not live)

    def feature_payload(guild_id: int, feature: Any, bot_permissions: int) -> dict[str, Any]:
        module = storage.get_module(guild_id, feature.id)
        missing = [] if bot_permissions & ADMINISTRATOR else [name for name in feature.required_bot_permissions if not bot_permissions & PERMISSION_BITS[name]]
        title, description = japanese_copy(feature.id)
        return {
            "id": feature.id, "category": feature.category, "parent": feature.parent,
            "title": title, "description": description, "fields": list(feature.fields),
            "required_fields": list(feature.required_fields), "required_bot_permissions": list(feature.required_bot_permissions),
            "enabled": module["enabled"], "settings": _serialize_resource_ids(module["settings"]), "revision": module["revision"],
            "missing_permissions": missing,
        }

    @router.get("/guilds/{guild_id}/overview")
    async def overview(request: Request, guild_id: int) -> dict[str, Any]:
        channels, roles, permissions = await resources(request, guild_id)
        features = [feature_payload(guild_id, feature, permissions) for feature in FEATURES]
        return {
            "guild_id": str(guild_id), "features": features,
            "resources": {"channels": channels, "roles": roles, "bot_permissions": str(permissions)},
            "moderation": {"summary": storage.moderation_summary(guild_id), "events": storage.recent_moderation_events(guild_id, limit=10), "lockdown": storage.active_lockdown(guild_id)},
        }

    @router.get("/guilds/{guild_id}/features")
    async def features(request: Request, guild_id: int) -> dict[str, Any]:
        _, _, permissions = await resources(request, guild_id)
        return {"items": [feature_payload(guild_id, feature, permissions) for feature in FEATURES]}

    @router.get("/guilds/{guild_id}/resources")
    async def guild_resources(request: Request, guild_id: int) -> dict[str, Any]:
        channels, roles, permissions = await resources(request, guild_id)
        return {"channels": channels, "roles": roles, "bot_permissions": str(permissions)}

    def provider_available(provider: str) -> bool:
        if settings is None:
            return True
        return {
            "youtube": True,
            "twitch": bool(settings.twitch_client_id and settings.twitch_client_secret and settings.dashboard_base_url and settings.social_webhook_secret),
            "x": bool(settings.x_bearer_token),
            "tiktok": importlib.util.find_spec("yt_dlp") is not None,
            "instagram": bool(settings.instagram_rss_url_template),
        }[provider]

    def social_payload(subscription: dict[str, Any]) -> dict[str, Any]:
        target = storage.social_target(int(subscription["target_id"])) if subscription.get("target_id") else None
        public_target = ({key: target.get(key) for key in ("id", "provider", "account_key", "external_id", "handle", "display_name", "avatar_url", "status", "last_error", "last_checked_at", "revision")} if target else None)
        return {
            **subscription,
            "id": int(subscription["id"]), "guild_id": str(subscription["guild_id"]),
            "channel_id": str(subscription["channel_id"]), "role_id": str(subscription["role_id"]) if subscription.get("role_id") else None,
            "event_channels": {key: str(value) for key, value in subscription.get("event_channels", {}).items()},
            "target": public_target,
        }

    @router.get("/guilds/{guild_id}/social")
    async def social_summary(request: Request, guild_id: int) -> dict[str, Any]:
        await manage(request, guild_id)
        health = storage.social_worker_health()
        subscriptions = storage.social_subscriptions(guild_id)
        return {"providers": [{"id": provider, "available": provider_available(provider), "events": list(PROVIDER_EVENTS[provider]),
            "count": sum(1 for item in subscriptions if item["provider"] == provider),
            "limit": int(getattr(settings, "social_max_subscriptions_per_provider", 10))} for provider in PROVIDERS],
            "worker": {**health, "online": bool(health and int(health["heartbeat_at"]) >= int(time.time()) - 30)} if health else {"online": False}}

    @router.get("/guilds/{guild_id}/social/{provider}/subscriptions")
    async def social_subscriptions(request: Request, guild_id: int, provider: str) -> dict[str, Any]:
        if provider not in PROVIDERS:
            raise HTTPException(404, detail={"code": "provider_not_found", "message": "通知サービスが見つかりません。"})
        await manage(request, guild_id)
        return {"items": [social_payload(item) for item in storage.social_subscriptions(guild_id, provider)],
                "available": provider_available(provider), "events": list(PROVIDER_EVENTS[provider]),
                "limit": int(getattr(settings, "social_max_subscriptions_per_provider", 10)),
                "variables": list(TEMPLATE_VARIABLES), "defaults": default_templates(provider)}

    async def checked_social_body(request: Request, guild_id: int, provider: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if provider not in PROVIDERS or not provider_available(provider):
            raise HTTPException(409, detail={"code": "provider_unavailable", "message": "この通知サービスは運用設定が完了していません。"})
        body = await request.json() if body is None else body
        value = validate_subscription(provider, body)
        channels, roles, permissions = await discord.guild_resources(guild_id, use_cache=False)
        text_channels = {int(item["id"]) for item in channels if int(item["type"]) in {0, 5}}
        role_ids = {int(item["id"]) for item in roles}
        if value["channel_id"] not in text_channels or any(channel not in text_channels for channel in value["event_channels"].values()):
            raise ValueError("channel")
        if value["role_id"] is not None and value["role_id"] not in role_ids:
            raise ValueError("role")
        if not ((permissions & ADMINISTRATOR) or (permissions & PERMISSION_BITS["send_messages"])):
            raise PermissionError("send_messages")
        return value

    @router.post("/guilds/{guild_id}/social/{provider}/subscriptions", status_code=201)
    async def create_social_subscription(request: Request, guild_id: int, provider: str) -> dict[str, Any]:
        csrf(request)
        await manage(request, guild_id, live=True)
        try:
            value = await checked_social_body(request, guild_id, provider)
            saved = storage.save_social_subscription_v2(guild_id, provider, max_count=int(getattr(settings, "social_max_subscriptions_per_provider", 10)), **value)
            storage.set_module(guild_id, f"{provider}_updates", enabled=any(bool(item["enabled"]) for item in storage.social_subscriptions(guild_id, provider)))
            return social_payload(saved)
        except OverflowError as exc:
            raise HTTPException(422, detail={"code": "social_limit", "message": "このサービスで登録できる上限に達しています。"}) from exc
        except (TypeError, ValueError, PermissionError) as exc:
            raise HTTPException(422, detail={"code": "social_invalid", "message": str(exc) or "対象アカウントと通知先を確認してください。"}) from exc

    @router.put("/guilds/{guild_id}/social/{provider}/subscriptions/{subscription_id}")
    async def update_social_subscription(request: Request, guild_id: int, provider: str, subscription_id: int) -> dict[str, Any]:
        csrf(request)
        await manage(request, guild_id, live=True)
        current = storage.social_subscription(subscription_id)
        if not current or int(current["guild_id"]) != guild_id or current["provider"] != provider:
            raise HTTPException(404, detail={"code": "subscription_not_found", "message": "登録が見つかりません。"})
        try:
            body = await request.json()
            value = await checked_social_body(request, guild_id, provider, body)
            if value["account_key"] != normalize_account(provider, str(current["account_id"])):
                raise ValueError("対象アカウントは変更できません。新しい登録を作成してください。")
            saved = storage.save_social_subscription_v2(guild_id, provider, subscription_id=subscription_id,
                expected_revision=int(body["revision"]) if body.get("revision") is not None else None, **value)
            storage.set_module(guild_id, f"{provider}_updates", enabled=any(bool(item["enabled"]) for item in storage.social_subscriptions(guild_id, provider)))
            return social_payload(saved)
        except RuntimeError as exc:
            raise HTTPException(409, detail={"code": "revision_conflict", "message": "別の管理者がこの登録を更新しました。再読み込みしてください。"}) from exc
        except (TypeError, ValueError, PermissionError) as exc:
            raise HTTPException(422, detail={"code": "social_invalid", "message": str(exc) or "登録内容を確認してください。"}) from exc

    @router.delete("/guilds/{guild_id}/social/{provider}/subscriptions/{subscription_id}", status_code=204)
    async def delete_social_subscription(request: Request, guild_id: int, provider: str, subscription_id: int, if_match: str | None = Header(default=None)) -> None:
        csrf(request)
        await manage(request, guild_id, live=True)
        current = storage.social_subscription(subscription_id)
        if not current or int(current["guild_id"]) != guild_id or current["provider"] != provider:
            raise HTTPException(404, detail={"code": "subscription_not_found", "message": "登録が見つかりません。"})
        if if_match is not None and int(if_match.strip('"')) != int(current.get("revision", 1)):
            raise HTTPException(409, detail={"code": "revision_conflict", "message": "別の管理者がこの登録を更新しました。"})
        storage.delete_social_subscription(guild_id, subscription_id)
        storage.set_module(guild_id, f"{provider}_updates", enabled=any(bool(item["enabled"]) for item in storage.social_subscriptions(guild_id, provider)))

    @router.post("/guilds/{guild_id}/social/{provider}/subscriptions/{subscription_id}/retry")
    async def retry_social_subscription(request: Request, guild_id: int, provider: str, subscription_id: int) -> dict[str, str]:
        csrf(request)
        await manage(request, guild_id, live=True)
        current = storage.social_subscription(subscription_id)
        if not current or int(current["guild_id"]) != guild_id or current["provider"] != provider or not current.get("target_id"):
            raise HTTPException(404, detail={"code": "subscription_not_found", "message": "登録が見つかりません。"})
        storage.request_social_target_retry(int(current["target_id"]))
        return {"status": "pending"}

    @router.post("/guilds/{guild_id}/social/{provider}/preview")
    async def preview_social_template(request: Request, guild_id: int, provider: str) -> dict[str, Any]:
        csrf(request)
        await manage(request, guild_id)
        try:
            body = await request.json()
            event = str(body.get("event") or PROVIDER_EVENTS[provider][0])
            template = validate_subscription(provider, {"account": "preview", "channel_id": 1, "events": [event], "templates": {event: body.get("template") or {}}})["templates"][event]
            sample = {"account": "Sample Creator", "handle": "sample", "title": "新しいコンテンツ", "text": "通知本文のプレビューです。",
                "url": "https://example.com/content", "platform": provider.title(), "event": event, "published_at": "2026-08-18 12:00",
                "thumbnail": "https://example.com/thumbnail.jpg", "avatar": "https://example.com/avatar.jpg", "viewer_count": "123"}
            return {key: render_template(str(value), sample, limit={"content": 1900, "title": 256, "description": 4096, "footer": 2048}.get(key, 500)) for key, value in template.items()}
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(422, detail={"code": "template_invalid", "message": str(exc) or "通知テンプレートを確認してください。"}) from exc

    def ticket_ids(value: dict[str, Any]) -> dict[str, Any]:
        result = dict(value)
        result.pop("encrypted_content", None)
        result.pop("form_answers_json", None)
        result.pop("payload_json", None)
        singular = ("guild_id", "channel_id", "message_id", "form_id", "team_id", "category_id", "thread_parent_channel_id",
                    "staff_notification_channel_id", "log_channel_id", "transcript_channel_id", "discord_container_id", "parent_channel_id",
                    "opener_id", "claimed_by", "closed_by", "panel_id", "notification_channel_id")
        plural = ("role_ids", "user_ids", "admin_user_ids", "required_role_ids", "mention_role_ids", "mention_user_ids", "panel_ids")
        for key in singular:
            if key in result:
                result[key] = str(result[key]) if result[key] not in (None, "") else None
        for key in plural:
            if key in result:
                result[key] = [str(item) for item in result.get(key, [])]
        return result

    async def validate_ticket_resources(guild_id: int, value: dict[str, Any]) -> None:
        channels, roles, bot_permissions = await discord.guild_resources(guild_id, use_cache=False)
        channel_types = {int(item["id"]): int(item["type"]) for item in channels}
        role_ids = {int(item["id"]) for item in roles}
        for key in ("log_channel_id", "transcript_channel_id", "thread_parent_channel_id", "staff_notification_channel_id", "notification_channel_id", "channel_id"):
            if value.get(key) and channel_types.get(int(value[key])) != 0:
                raise ValueError(key)
        if value.get("category_id") and channel_types.get(int(value["category_id"])) != 4:
            raise ValueError("category_id")
        for key in ("role_ids", "required_role_ids", "mention_role_ids"):
            if any(int(item) not in role_ids for item in value.get(key, [])):
                raise ValueError(key)
        required: set[str] = set()
        if value.get("category_id"):
            required.update({"manage_channels", "send_messages", "read_message_history", "manage_messages"})
        if value.get("thread_parent_channel_id"):
            required.update({"manage_threads", "create_private_threads", "send_messages_in_threads", "read_message_history"})
        if value.get("channel_id"):
            required.update({"send_messages", "embed_links"})
        if not bot_permissions & ADMINISTRATOR:
            missing = [name for name in required if not bot_permissions & PERMISSION_BITS[name]]
            if missing:
                raise ValueError("bot_permissions:" + ",".join(sorted(missing)))

    @router.get("/guilds/{guild_id}/tickets")
    async def ticket_overview(request: Request, guild_id: int) -> dict[str, Any]:
        tickets_available(guild_id)
        actor, administrator = await ticket_actor(request, guild_id)
        recent = []
        for item in ticket_repository.tickets(guild_id, limit=10):
            try:
                await ticket_subject_access(request, guild_id, item, actor, administrator)
                recent.append(ticket_ids(item))
            except HTTPException as exc:
                if exc.status_code != 403: raise
        return {"settings": ticket_ids(ticket_repository.settings(guild_id)), "summary": ticket_repository.summary(guild_id),
                "recent": recent,
                "transcript_storage": {"available": ticket_transcripts.available, "s3_configured": bool(settings.ticket_s3_bucket)}, "can_manage": administrator}

    @router.get("/guilds/{guild_id}/tickets/settings")
    async def ticket_settings(request: Request, guild_id: int) -> dict[str, Any]:
        tickets_available(guild_id); await ticket_actor(request, guild_id, require_manage=True)
        return ticket_ids(ticket_repository.settings(guild_id))

    @router.put("/guilds/{guild_id}/tickets/settings")
    async def save_ticket_settings(request: Request, guild_id: int) -> dict[str, Any]:
        csrf(request); tickets_available(guild_id); actor, _ = await ticket_actor(request, guild_id, require_manage=True)
        try:
            body = await request.json(); value = validate_settings(body)
            await validate_ticket_resources(guild_id, value)
            if value["enabled"] and not ticket_transcripts.available:
                raise ValueError("TICKET_ENCRYPTION_KEY")
            saved = ticket_repository.save_settings(guild_id, value, int(body["revision"]) if body.get("revision") else None)
            storage.set_module(guild_id, "tickets", enabled=saved["enabled"])
            for ticket in ticket_repository.tickets(guild_id, status="open", limit=200): ticket_service.schedule_ticket(ticket)
            ticket_repository.audit(guild_id, "settings_updated", actor, detail={})
            return ticket_ids(saved)
        except RuntimeError as exc:
            raise HTTPException(409, detail={"code": "revision_conflict", "message": "別の管理者がTicket設定を更新しました。"}) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, detail={"code": "ticket_settings_invalid", "message": str(exc) or "Ticket設定を確認してください。"}) from exc

    @router.get("/guilds/{guild_id}/tickets/forms")
    async def ticket_forms(request: Request, guild_id: int) -> dict[str, Any]:
        tickets_available(guild_id); await ticket_actor(request, guild_id, require_manage=True)
        return {"items": ticket_repository.forms(guild_id)}

    @router.post("/guilds/{guild_id}/tickets/forms", status_code=201)
    async def create_ticket_form(request: Request, guild_id: int) -> dict[str, Any]:
        csrf(request); tickets_available(guild_id); await ticket_actor(request, guild_id, require_manage=True)
        try: return ticket_repository.save_form(guild_id, validate_form(await request.json()))
        except (TypeError, ValueError) as exc: raise HTTPException(422, detail={"code": "ticket_form_invalid", "message": str(exc)}) from exc

    @router.put("/guilds/{guild_id}/tickets/forms/{form_id}")
    async def update_ticket_form(request: Request, guild_id: int, form_id: int) -> dict[str, Any]:
        csrf(request); tickets_available(guild_id); await ticket_actor(request, guild_id, require_manage=True); body = await request.json()
        try: return ticket_repository.save_form(guild_id, validate_form(body), form_id, int(body["revision"]) if body.get("revision") else None)
        except RuntimeError as exc: raise HTTPException(409, detail={"code": "revision_conflict", "message": "Formが更新されています。"}) from exc
        except (KeyError, TypeError, ValueError) as exc: raise HTTPException(422, detail={"code": "ticket_form_invalid", "message": str(exc)}) from exc

    @router.get("/guilds/{guild_id}/tickets/teams")
    async def ticket_teams(request: Request, guild_id: int) -> dict[str, Any]:
        tickets_available(guild_id); await ticket_actor(request, guild_id, require_manage=True)
        return {"items": [ticket_ids(item) for item in ticket_repository.teams(guild_id)]}

    @router.post("/guilds/{guild_id}/tickets/teams", status_code=201)
    async def create_ticket_team(request: Request, guild_id: int) -> dict[str, Any]:
        csrf(request); tickets_available(guild_id); await ticket_actor(request, guild_id, require_manage=True); body = await request.json()
        try:
            await validate_ticket_resources(guild_id, body)
            return ticket_ids(ticket_repository.save_team(guild_id, body))
        except (TypeError, ValueError) as exc: raise HTTPException(422, detail={"code": "ticket_team_invalid", "message": str(exc)}) from exc

    @router.put("/guilds/{guild_id}/tickets/teams/{team_id}")
    async def update_ticket_team(request: Request, guild_id: int, team_id: int) -> dict[str, Any]:
        csrf(request); tickets_available(guild_id); await ticket_actor(request, guild_id, require_manage=True); body = await request.json()
        try:
            await validate_ticket_resources(guild_id, body)
            return ticket_ids(ticket_repository.save_team(guild_id, body, team_id, int(body["revision"]) if body.get("revision") else None))
        except RuntimeError as exc: raise HTTPException(409, detail={"code": "revision_conflict", "message": "Teamが更新されています。"}) from exc
        except (KeyError, TypeError, ValueError) as exc: raise HTTPException(422, detail={"code": "ticket_team_invalid", "message": str(exc)}) from exc

    @router.get("/guilds/{guild_id}/tickets/panels")
    async def ticket_panels(request: Request, guild_id: int) -> dict[str, Any]:
        tickets_available(guild_id); await ticket_actor(request, guild_id, require_manage=True)
        return {"items": [ticket_ids(item) for item in ticket_repository.panels(guild_id)]}

    @router.post("/guilds/{guild_id}/tickets/panels", status_code=201)
    async def create_ticket_panel(request: Request, guild_id: int) -> dict[str, Any]:
        csrf(request); tickets_available(guild_id); await ticket_actor(request, guild_id, require_manage=True); body = await request.json()
        try:
            value = validate_panel(body); await validate_ticket_resources(guild_id, value)
            return ticket_ids(ticket_repository.save_panel(guild_id, value))
        except (TypeError, ValueError) as exc: raise HTTPException(422, detail={"code": "ticket_panel_invalid", "message": str(exc)}) from exc

    @router.put("/guilds/{guild_id}/tickets/panels/{panel_id}")
    async def update_ticket_panel(request: Request, guild_id: int, panel_id: int) -> dict[str, Any]:
        csrf(request); tickets_available(guild_id); await ticket_actor(request, guild_id, require_manage=True); body = await request.json()
        try:
            value = validate_panel(body); await validate_ticket_resources(guild_id, value)
            saved = ticket_repository.save_panel(guild_id, value, panel_id, int(body["revision"]) if body.get("revision") else None)
            for ticket in ticket_repository.tickets(guild_id, status="open", limit=200):
                if int(ticket["panel_id"]) == panel_id: ticket_service.schedule_ticket(ticket)
            return ticket_ids(saved)
        except RuntimeError as exc: raise HTTPException(409, detail={"code": "revision_conflict", "message": "Panelが更新されています。"}) from exc
        except (KeyError, TypeError, ValueError) as exc: raise HTTPException(422, detail={"code": "ticket_panel_invalid", "message": str(exc)}) from exc

    @router.get("/guilds/{guild_id}/tickets/panel-messages")
    async def ticket_panel_messages(request: Request, guild_id: int) -> dict[str, Any]:
        tickets_available(guild_id); await ticket_actor(request, guild_id, require_manage=True)
        return {"items": [ticket_ids(item) for item in ticket_repository.panel_messages(guild_id)]}

    @router.post("/guilds/{guild_id}/tickets/panel-messages", status_code=201)
    async def create_ticket_panel_message(request: Request, guild_id: int) -> dict[str, Any]:
        csrf(request); tickets_available(guild_id); await ticket_actor(request, guild_id, require_manage=True); body = await request.json()
        try:
            await validate_ticket_resources(guild_id, body)
            return ticket_ids(ticket_repository.save_panel_message(guild_id, body))
        except (TypeError, ValueError) as exc: raise HTTPException(422, detail={"code": "ticket_panel_message_invalid", "message": str(exc)}) from exc

    @router.get("/guilds/{guild_id}/tickets/tags")
    async def ticket_tags(request: Request, guild_id: int) -> dict[str, Any]:
        tickets_available(guild_id); await ticket_actor(request, guild_id)
        return {"items": ticket_repository.tags(guild_id)}

    @router.post("/guilds/{guild_id}/tickets/tags", status_code=201)
    async def save_ticket_tag(request: Request, guild_id: int) -> dict[str, Any]:
        csrf(request); tickets_available(guild_id); actor, _ = await ticket_actor(request, guild_id); body = await request.json()
        try: return ticket_repository.save_tag(guild_id, str(body.get("name", "")), str(body.get("content", "")), actor)
        except ValueError as exc: raise HTTPException(422, detail={"code": "ticket_tag_invalid", "message": "Tag名は英数字・_・-、本文は2000文字以内で入力してください。"}) from exc

    @router.delete("/guilds/{guild_id}/tickets/tags/{tag_id}", status_code=204)
    async def delete_ticket_tag(request: Request, guild_id: int, tag_id: int) -> Response:
        csrf(request); tickets_available(guild_id); await ticket_actor(request, guild_id, require_manage=True)
        if not ticket_repository.delete_tag(guild_id, tag_id): raise HTTPException(404, detail={"code": "ticket_tag_not_found", "message": "Tagが見つかりません。"})
        return Response(status_code=204)

    @router.get("/guilds/{guild_id}/tickets/stats")
    async def ticket_stats(request: Request, guild_id: int) -> dict[str, Any]:
        tickets_available(guild_id); await ticket_actor(request, guild_id, require_manage=True)
        return ticket_repository.statistics(guild_id)

    @router.get("/guilds/{guild_id}/tickets/items")
    async def ticket_items(request: Request, guild_id: int, status: str | None = None, before: int | None = None) -> dict[str, Any]:
        tickets_available(guild_id); actor, administrator = await ticket_actor(request, guild_id)
        visible = []
        for item in ticket_repository.tickets(guild_id, status=status, before=before):
            try:
                await ticket_subject_access(request, guild_id, item, actor, administrator)
                visible.append(ticket_ids(item))
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
        return {"items": visible, "next": int(visible[-1]["id"]) if visible else None}

    @router.get("/guilds/{guild_id}/tickets/items/{ticket_id}")
    async def ticket_detail(request: Request, guild_id: int, ticket_id: int, after: int = 0) -> dict[str, Any]:
        tickets_available(guild_id); actor, administrator = await ticket_actor(request, guild_id)
        ticket = ticket_repository.ticket(ticket_id)
        if not ticket or int(ticket["guild_id"]) != guild_id: raise HTTPException(404, detail={"code": "ticket_not_found", "message": "Ticketが見つかりません。"})
        await ticket_subject_access(request, guild_id, ticket, actor, administrator)
        messages = ticket_repository.messages(ticket_id, after=after)
        safe_ticket = ticket_ids(ticket)
        safe_ticket["form_answers"] = {key: ticket_transcripts.decrypt_text(value) for key, value in dict(ticket.get("form_answers") or {}).items()}
        return {"ticket": safe_ticket, "panel": ticket_ids(ticket_repository.panel(guild_id, int(ticket["panel_id"])) or {}),
                "messages": [{**ticket_ids(item), "content": ticket_transcripts.decrypt_text(item.get("encrypted_content"))} for item in messages],
                "transcript": ticket_ids(ticket_repository.transcript_for_ticket(ticket_id) or {}), "outbox": ticket_repository.outbox(ticket_id)}

    @router.post("/guilds/{guild_id}/tickets/items/{ticket_id}/reply", status_code=202)
    async def ticket_reply(request: Request, guild_id: int, ticket_id: int) -> dict[str, Any]:
        csrf(request); tickets_available(guild_id); actor, administrator = await ticket_actor(request, guild_id); body = await request.json()
        ticket = ticket_repository.ticket(ticket_id)
        if not ticket or int(ticket["guild_id"]) != guild_id: raise HTTPException(404, detail={"code": "ticket_not_found", "message": "Ticketが見つかりません。"})
        await ticket_subject_access(request, guild_id, ticket, actor, administrator)
        user = await discord.current_user(token(request)); panel = ticket_repository.panel(guild_id, int(ticket["panel_id"])) or {}
        try:
            item = ticket_service.queue_reply(ticket_id, actor, user.get("global_name") or user["username"], str(body.get("content", "")),
                anonymous=bool(body.get("anonymous") or panel.get("anonymous_dashboard_replies")), note=bool(body.get("note")))
            return {"id": item["id"], "status": item["status"]}
        except TicketValidationError as exc: raise HTTPException(422, detail={"code": exc.code, "message": str(exc)}) from exc

    @router.post("/guilds/{guild_id}/tickets/items/{ticket_id}/action", status_code=202)
    async def ticket_action(request: Request, guild_id: int, ticket_id: int) -> dict[str, Any]:
        csrf(request); tickets_available(guild_id); actor, administrator = await ticket_actor(request, guild_id); body = await request.json()
        ticket = ticket_repository.ticket(ticket_id)
        if not ticket or int(ticket["guild_id"]) != guild_id: raise HTTPException(404, detail={"code": "ticket_not_found", "message": "Ticketが見つかりません。"})
        await ticket_subject_access(request, guild_id, ticket, actor, administrator)
        action = str(body.get("action", ""))
        if action not in {"claim", "unclaim", "close", "reopen", "delete", "exclude_auto_close"}: raise HTTPException(422, detail={"code": "ticket_action_invalid", "message": "操作を確認してください。"})
        item = ticket_repository.queue_outbox(ticket_id, action, actor, {"reason": str(body.get("reason", ""))[:1000], "revision": body.get("revision"), "excluded": body.get("excluded", True)})
        return {"id": item["id"], "status": item["status"]}

    @router.get("/tickets/transcripts/{transcript_id}")
    async def ticket_transcript(request: Request, transcript_id: int) -> dict[str, Any]:
        if not ticket_repository or not ticket_transcripts: raise HTTPException(404)
        transcript = ticket_repository.transcript(transcript_id)
        if not transcript or transcript.get("status") != "ready" or int(transcript["expires_at"]) < int(time.time()): raise HTTPException(404, detail={"code": "transcript_not_found", "message": "Transcriptが見つかりません。"})
        access = token(request); user = await discord.current_user(access); user_id = int(user["id"])
        if user_id != int(transcript["opener_id"]):
            actor, administrator = await ticket_actor(request, int(transcript["guild_id"]))
            ticket = ticket_repository.ticket(int(transcript["ticket_id"]))
            if ticket:
                await ticket_subject_access(request, int(transcript["guild_id"]), ticket, actor, administrator)
        ticket_repository.audit(int(transcript["guild_id"]), "transcript_viewed", user_id, int(transcript["ticket_id"]), {"transcript_id": transcript_id})
        payload = await ticket_transcripts.load(transcript["backend"], transcript["object_key"], transcript["content_hash"])
        panel = ticket_repository.panel(int(transcript["guild_id"]), int(transcript["panel_id"]))
        payload["feedback_enabled"] = bool(panel and panel.get("feedback_enabled"))
        return payload

    @router.get("/tickets/attachments/{attachment_id}")
    async def ticket_attachment(request: Request, attachment_id: int) -> Response:
        if not ticket_repository or not ticket_transcripts: raise HTTPException(404)
        attachment = ticket_repository.attachment(attachment_id)
        if not attachment or attachment.get("status") != "ready": raise HTTPException(404, detail={"code": "attachment_not_found", "message": "添付ファイルが見つかりません。"})
        access = token(request); user = await discord.current_user(access); user_id = int(user["id"])
        if user_id != int(attachment["opener_id"]):
            actor, administrator = await ticket_actor(request, int(attachment["guild_id"]))
            ticket = ticket_repository.ticket(int(attachment["ticket_id"]))
            if ticket: await ticket_subject_access(request, int(attachment["guild_id"]), ticket, actor, administrator)
        content = await ticket_transcripts.load_attachment(str(attachment["backend"]), str(attachment["object_key"]), str(attachment["content_hash"]))
        ticket_repository.audit(int(attachment["guild_id"]), "attachment_downloaded", user_id, int(attachment["ticket_id"]), {"attachment_id": attachment_id})
        filename = quote(str(attachment["filename"]), safe="")
        return Response(content, media_type="application/octet-stream", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}", "X-Content-Type-Options": "nosniff"})

    @router.post("/tickets/{ticket_id}/feedback", status_code=201)
    async def ticket_feedback(request: Request, ticket_id: int) -> dict[str, Any]:
        csrf(request)
        if not ticket_repository or not ticket_transcripts: raise HTTPException(404)
        ticket = ticket_repository.ticket(ticket_id)
        if not ticket: raise HTTPException(404, detail={"code": "ticket_not_found", "message": "Ticketが見つかりません。"})
        panel = ticket_repository.panel(int(ticket["guild_id"]), int(ticket["panel_id"]))
        if not panel or not panel.get("feedback_enabled"): raise HTTPException(403, detail={"code": "feedback_disabled", "message": "このTicketでは評価を受け付けていません。"})
        user = await discord.current_user(token(request)); user_id = int(user["id"]); body = await request.json()
        comment = str(body.get("comment") or "").strip()
        if len(comment) > 1000: raise HTTPException(422, detail={"code": "feedback_invalid", "message": "コメントは1000文字以内で入力してください。"})
        try:
            saved = ticket_repository.save_feedback(ticket_id, user_id, int(body.get("rating", 0)), ticket_transcripts.encrypt_text(comment) if comment else None)
            ticket_repository.audit(int(ticket["guild_id"]), "feedback_submitted", user_id, ticket_id, {"rating": saved["rating"]})
            return {"rating": saved["rating"], "created_at": saved["created_at"]}
        except PermissionError as exc: raise HTTPException(403, detail={"code": "feedback_forbidden", "message": "このTicketを評価できません。"}) from exc
        except (TypeError, ValueError) as exc: raise HTTPException(422, detail={"code": "feedback_invalid", "message": "評価は1～5で指定してください。"}) from exc
        except sqlite3.IntegrityError as exc: raise HTTPException(409, detail={"code": "feedback_exists", "message": "このTicketは評価済みです。"}) from exc

    @router.get("/guilds/{guild_id}/modules/{module_id}")
    async def module(request: Request, guild_id: int, module_id: str) -> dict[str, Any]:
        await manage(request, guild_id)
        try:
            feature = get_feature(module_id)
        except ValueError as exc:
            raise HTTPException(404, detail={"code": "module_not_found", "message": "機能が見つかりません。"}) from exc
        _, _, permissions = await discord.guild_resources(guild_id)
        return feature_payload(guild_id, feature, permissions)

    def validate_resource_ids(settings: dict[str, Any], channels: set[int], roles: set[int]) -> None:
        for key, value in settings.items():
            if value in (None, "", []):
                continue
            kind = _resource_kind(key)
            if kind is None:
                continue
            resource_ids, multiple = (channels if kind[0] == "channel" else roles), kind[1]
            values = value if multiple else [value]
            if not isinstance(values, list) or any(int(item) not in resource_ids for item in values):
                raise ValueError(key)

    @router.put("/guilds/{guild_id}/modules/{module_id}")
    async def save_module(request: Request, guild_id: int, module_id: str) -> dict[str, Any]:
        csrf(request)
        await manage(request, guild_id, live=True)
        try:
            get_feature(module_id)
            body = await request.json()
            channels, roles, _ = await discord.guild_resources(guild_id, use_cache=False)
            values = body.get("settings", {})
            if not isinstance(values, dict):
                raise ValueError("settings")
            validate_resource_ids(values, {int(item["id"]) for item in channels}, {int(item["id"]) for item in roles})
            saved = storage.set_module(guild_id, module_id, enabled=bool(body.get("enabled")), settings=_normalize_resource_ids(values),
                                       expected_revision=int(body["revision"]) if body.get("revision") is not None else None)
            return {**saved, "settings": _serialize_resource_ids(saved["settings"])}
        except RuntimeError as exc:
            raise HTTPException(409, detail={"code": "revision_conflict", "message": "別の管理者が設定を更新しました。再読み込みしてください。"}) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, detail={"code": "module_invalid", "message": "サーバー内のチャンネル、ロール、設定値を確認してください。"}) from exc

    @router.get("/guilds/{guild_id}/moderation/{family}/rules")
    async def rules(request: Request, guild_id: int, family: str) -> dict[str, Any]:
        if family not in FAMILY_TRIGGERS:
            raise HTTPException(404, detail={"code": "family_not_found", "message": "ルール種別が見つかりません。"})
        await manage(request, guild_id)
        return {"items": [_serialize_rule_resource_ids(item) for item in storage.moderation_rules(guild_id, family=family)], "trigger_types": FAMILY_TRIGGERS[family]}

    @router.get("/guilds/{guild_id}/moderation/{family}/rules/{rule_id}")
    async def rule(request: Request, guild_id: int, family: str, rule_id: int) -> dict[str, Any]:
        await manage(request, guild_id)
        value = storage.moderation_rule(guild_id, rule_id)
        if not value or value["family"] != family:
            raise HTTPException(404, detail={"code": "rule_not_found", "message": "ルールが見つかりません。"})
        return _serialize_rule_resource_ids(value)

    def normalized_rule(body: dict[str, Any], family: str) -> dict[str, Any]:
        trigger = str(body.get("trigger_type", ""))
        if family not in FAMILY_TRIGGERS or trigger not in FAMILY_TRIGGERS[family]:
            raise ValueError("trigger_type")
        defaults = default_rule(trigger)
        value = {
            **defaults,
            **body,
            "family": family,
            "trigger_config": {
                **defaults["trigger_config"],
                **dict(body.get("trigger_config") or {}),
            },
        }
        value["event_type"] = str(body.get("event_type") or ("member_join" if trigger in {"join_rate", "new_account_ratio"} else "member_remove" if trigger == "leave_rate" else "reaction_add" if trigger.startswith("reaction_") else "message_create"))
        return validate_rule(value)

    @router.post("/guilds/{guild_id}/moderation/{family}/rules", status_code=201)
    async def create_rule(request: Request, guild_id: int, family: str) -> dict[str, Any]:
        csrf(request)
        await manage(request, guild_id, live=True)
        try:
            value = normalized_rule(await request.json(), family)
            value["priority"] = storage.next_moderation_rule_priority(guild_id, family)
            return _serialize_rule_resource_ids(storage.save_moderation_rule(guild_id, value))
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, detail={"code": "rule_invalid", "message": str(exc) or "ルールを確認してください。"}) from exc

    @router.put("/guilds/{guild_id}/moderation/{family}/rules/order")
    async def reorder_rules(request: Request, guild_id: int, family: str) -> dict[str, Any]:
        csrf(request)
        await manage(request, guild_id, live=True)
        if family not in FAMILY_TRIGGERS:
            raise HTTPException(404, detail={"code": "family_not_found", "message": "ルール種別が見つかりません。"})
        try:
            body = await request.json()
            items = body.get("items")
            if not isinstance(items, list):
                raise ValueError("items")
            return {"items": [_serialize_rule_resource_ids(item) for item in storage.reorder_moderation_rules(guild_id, family, items)]}
        except RuntimeError as exc:
            raise HTTPException(409, detail={"code": "revision_conflict", "message": "別の管理者がルール一覧を更新しました。再読み込みしてください。"}) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, detail={"code": "rule_order_invalid", "message": "ルールの順序を再読み込みして、もう一度保存してください。"}) from exc

    @router.put("/guilds/{guild_id}/moderation/{family}/rules/{rule_id}")
    async def update_rule(request: Request, guild_id: int, family: str, rule_id: int) -> dict[str, Any]:
        csrf(request)
        await manage(request, guild_id, live=True)
        body, current = await request.json(), storage.moderation_rule(guild_id, rule_id)
        if not current or current["family"] != family:
            raise HTTPException(404, detail={"code": "rule_not_found", "message": "ルールが見つかりません。"})
        if body.get("revision") is not None and int(body["revision"]) != int(current["revision"]):
            raise HTTPException(409, detail={"code": "revision_conflict", "message": "別の管理者がルールを更新しました。再読み込みしてください。"})
        try:
            value = normalized_rule(body, family)
            value["priority"] = current["priority"]
            return _serialize_rule_resource_ids(storage.save_moderation_rule(guild_id, value, rule_id))
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, detail={"code": "rule_invalid", "message": str(exc) or "ルールを確認してください。"}) from exc

    @router.delete("/guilds/{guild_id}/moderation/{family}/rules/{rule_id}", status_code=204)
    async def delete_rule(request: Request, guild_id: int, family: str, rule_id: int, if_match: str | None = Header(default=None)) -> None:
        csrf(request)
        await manage(request, guild_id, live=True)
        current = storage.moderation_rule(guild_id, rule_id)
        if not current or current["family"] != family:
            raise HTTPException(404, detail={"code": "rule_not_found", "message": "ルールが見つかりません。"})
        if if_match is not None and int(if_match.strip('"')) != int(current["revision"]):
            raise HTTPException(409, detail={"code": "revision_conflict", "message": "別の管理者がルールを更新しました。"})
        storage.delete_moderation_rule(guild_id, rule_id)

    @router.post("/guilds/{guild_id}/moderation/{family}/rules/{rule_id}/duplicate", status_code=201)
    async def duplicate_rule(request: Request, guild_id: int, family: str, rule_id: int) -> dict[str, Any]:
        csrf(request)
        await manage(request, guild_id, live=True)
        current = storage.moderation_rule(guild_id, rule_id)
        if not current or current["family"] != family:
            raise HTTPException(404, detail={"code": "rule_not_found", "message": "ルールが見つかりません。"})
        copy = {key: value for key, value in current.items() if key not in {"id", "guild_id", "revision", "created_at", "updated_at", "legacy_rule_id"}}
        copy.update({"name": f"{current['name']} (コピー)"[:100], "enabled": False, "priority": storage.next_moderation_rule_priority(guild_id, family)})
        return _serialize_rule_resource_ids(storage.save_moderation_rule(guild_id, validate_rule(copy)))

    @router.post("/guilds/{guild_id}/moderation/{family}/preview")
    async def preview(request: Request, guild_id: int, family: str) -> dict[str, Any]:
        csrf(request)
        await manage(request, guild_id)
        body = await request.json()
        try:
            value = normalized_rule(body.get("rule", {}), family)
            test = body.get("input", {})
            context = MessageContext(guild_id, 1, int(test.get("channel_id") or 1), content=str(test.get("content", ""))[:4000],
                mention_count=max(0, min(int(test.get("mentions", 0)), 100)), attachment_count=max(0, min(int(test.get("attachments", 0)), 20)),
                sticker_count=max(0, min(int(test.get("stickers", 0)), 100)), event_type=value["event_type"])
            engine, matches = AutoModEngine(), []
            repeats = int(value["trigger_config"].get("limit", 1)) if value["trigger_type"].endswith("rate") or value["trigger_type"] in {"duplicate", "reaction_burst", "new_account_ratio", "emoji_sticker_rate"} else 1
            for _ in range(max(1, min(repeats, 100))):
                matches = await engine.evaluate(context, [{**value, "id": 1}])
            return {"matched": bool(matches), "reason": matches[0].reason if matches else "一致しませんでした。", "trace": ["actor", "global_exemptions", "family_exemptions", "rule_exemptions", "conditions", "trigger"]}
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, detail={"code": "preview_invalid", "message": "ルールまたはテスト入力を確認してください。"}) from exc

    @router.get("/guilds/{guild_id}/moderation/events")
    async def events(request: Request, guild_id: int, family: str | None = None, user_id: int | None = None, limit: int = 50) -> dict[str, Any]:
        await manage(request, guild_id)
        return {"items": storage.recent_moderation_events(guild_id, family=family, user_id=user_id, limit=limit)}

    @router.get("/guilds/{guild_id}/moderation/infractions/{user_id}")
    async def infractions(request: Request, guild_id: int, user_id: int) -> dict[str, Any]:
        await manage(request, guild_id)
        return {"user_id": str(user_id), "active_points": storage.active_points(guild_id, user_id), "cases": storage.recent_cases(guild_id, user_id, 100)}

    @router.post("/guilds/{guild_id}/moderation/actions", status_code=202)
    async def action(request: Request, guild_id: int) -> dict[str, Any]:
        csrf(request)
        access = await manage(request, guild_id, live=True)
        user, body = await discord.current_user(access, use_cache=False), await request.json()
        action_name, reason = str(body.get("action", "")), str(body.get("reason", "")).strip()[:500]
        if action_name not in ALLOWED_ACTIONS or not reason or body.get("confirmed") is not True:
            raise HTTPException(422, detail={"code": "action_invalid", "message": "処置、理由、確認内容を確認してください。"})
        if not storage.module_enabled(guild_id, "moderation"):
            raise HTTPException(409, detail={"code": "moderation_disabled", "message": "Moderationを有効にしてから処置を実行してください。"})
        try:
            target_user_id = int(body["target_user_id"]) if body.get("target_user_id") else None
            channel_id = int(body["channel_id"]) if body.get("channel_id") else None
            channels, _, bot_permissions = await discord.guild_resources(guild_id, use_cache=False)
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
            if action_name in target_actions and (target_user_id is None or target_user_id <= 0):
                raise ValueError("target user is required")
            if action_name in channel_actions and (channel_id is None or channel_id not in text_channel_ids):
                raise ValueError("a text channel from this server is required")
            if channel_id is not None and channel_id not in guild_channel_ids:
                raise ValueError("channel belongs to another server")
            confirmation = str(body.get("confirmation", "")).strip()
            expected = str(guild_id) if action_name == "lockdown" else str(target_user_id or "")
            if action_name in {"ban", "softban", "lockdown"} and confirmation != expected:
                raise ValueError("typed confirmation does not match")
            permission = required_permissions.get(action_name)
            if permission and not ((bot_permissions & ADMINISTRATOR) or (bot_permissions & PERMISSION_BITS[permission])):
                raise PermissionError(f"missing {permission}")
        except (TypeError, ValueError, PermissionError) as exc:
            raise HTTPException(422, detail={"code": "action_invalid", "message": "対象、チャンネル、Bot権限、確認入力を確認してください。"}) from exc
        request_id = storage.enqueue_moderation_action(guild_id, int(user["id"]), action_name,
            target_user_id=target_user_id, channel_id=channel_id, reason=reason,
            options={"duration_minutes": max(1, min(int(body.get("duration_minutes", 10)), 525600)), "count": max(1, min(int(body.get("count", 10)), 100))},
            dedupe_key=f"dashboard-v2:{guild_id}:{secrets.token_urlsafe(16)}")
        return {"request_id": request_id, "status": "queued"}

    return router
