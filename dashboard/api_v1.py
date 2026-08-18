"""Versioned JSON API consumed by the dashboard v2 SPA."""
from __future__ import annotations

import secrets
import time
import importlib.util
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from automod import AutoModEngine, MessageContext, default_rule, validate_rule
from dashboard.discord_api import ADMINISTRATOR, PERMISSION_BITS
from feature_registry import FEATURES, get_feature, japanese_copy
from social_models import PROVIDERS, PROVIDER_EVENTS, TEMPLATE_VARIABLES, default_templates, normalize_account, render_template, validate_subscription


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
        values = await discord.manageable_guilds(token(request))
        return {"items": [{"id": str(item["id"]), "name": item["name"], "icon": item.get("icon")} for item in values]}

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
