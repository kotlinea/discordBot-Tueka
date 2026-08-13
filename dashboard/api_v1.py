"""Versioned JSON API consumed by the dashboard v2 SPA."""
from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from automod import AutoModEngine, MessageContext, default_rule, validate_rule
from dashboard.discord_api import ADMINISTRATOR, PERMISSION_BITS
from feature_registry import FEATURES, get_feature, japanese_copy


FAMILY_TRIGGERS = {
    "automod": ("keyword", "regex", "safe_browsing", "phishing_link", "discord_invite", "domain", "caps", "emoji_sticker_rate", "media_only", "honeypot"),
    "anti_spam": ("message_rate", "duplicate", "mention_rate", "link_rate", "attachment_rate", "reaction_rate", "reaction_burst"),
    "anti_raid": ("join_rate", "leave_rate", "new_account_ratio", "new_member_activity"),
}
MODERATION_SECTIONS = ("automod", "anti_spam", "anti_raid", "infractions", "moderation_actions", "moderation_logs")
ALLOWED_ACTIONS = {"warn", "timeout", "untimeout", "kick", "ban", "unban", "softban", "purge", "lock", "unlock", "lockdown", "unlockdown"}


def create_api_router(storage: Any, discord: Any) -> APIRouter:
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
        return {
            "user": {"id": str(user["id"]), "name": user.get("global_name") or user["username"], "avatar": user.get("avatar")},
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
            "enabled": module["enabled"], "settings": module["settings"], "revision": module["revision"],
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
            if key.endswith("channel_id") and int(value) not in channels:
                raise ValueError(key)
            if key.endswith("channel_ids") and any(int(item) not in channels for item in value):
                raise ValueError(key)
            if key.endswith("role_id") and int(value) not in roles:
                raise ValueError(key)
            if key.endswith("role_ids") and any(int(item) not in roles for item in value):
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
            return storage.set_module(guild_id, module_id, enabled=bool(body.get("enabled")), settings=values,
                                      expected_revision=int(body["revision"]) if body.get("revision") is not None else None)
        except RuntimeError as exc:
            raise HTTPException(409, detail={"code": "revision_conflict", "message": "別の管理者が設定を更新しました。再読み込みしてください。"}) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, detail={"code": "module_invalid", "message": "サーバー内のチャンネル、ロール、設定値を確認してください。"}) from exc

    @router.get("/guilds/{guild_id}/moderation/{family}/rules")
    async def rules(request: Request, guild_id: int, family: str) -> dict[str, Any]:
        if family not in FAMILY_TRIGGERS:
            raise HTTPException(404, detail={"code": "family_not_found", "message": "ルール種別が見つかりません。"})
        await manage(request, guild_id)
        return {"items": storage.moderation_rules(guild_id, family=family), "trigger_types": FAMILY_TRIGGERS[family]}

    @router.get("/guilds/{guild_id}/moderation/{family}/rules/{rule_id}")
    async def rule(request: Request, guild_id: int, family: str, rule_id: int) -> dict[str, Any]:
        await manage(request, guild_id)
        value = storage.moderation_rule(guild_id, rule_id)
        if not value or value["family"] != family:
            raise HTTPException(404, detail={"code": "rule_not_found", "message": "ルールが見つかりません。"})
        return value

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
            return storage.save_moderation_rule(guild_id, normalized_rule(await request.json(), family))
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, detail={"code": "rule_invalid", "message": str(exc) or "ルールを確認してください。"}) from exc

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
            return storage.save_moderation_rule(guild_id, normalized_rule(body, family), rule_id)
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
        copy.update({"name": f"{current['name']} (コピー)"[:100], "enabled": False})
        return storage.save_moderation_rule(guild_id, validate_rule(copy))

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
