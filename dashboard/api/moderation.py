"""Moderation API routes."""
from __future__ import annotations
from .errors import api_error, revision_conflict, check_revision
from fastapi import Depends
import secrets
from typing import Any
from fastapi import APIRouter, Header, Request
from moderation import AutoModEngine, MessageContext, default_rule, validate_rule
from dashboard.discord_api import ADMINISTRATOR, PERMISSION_BITS
from .context import ApiContext
from .dependencies import ApiDependencies
from .serialization import _serialize_rule_resource_ids
FAMILY_TRIGGERS = {'automod': ('keyword', 'regex', 'safe_browsing', 'phishing_link', 'discord_invite', 'domain', 'caps', 'emoji_sticker_rate', 'media_only', 'honeypot'), 'anti_spam': ('message_rate', 'duplicate', 'mention_rate', 'link_rate', 'attachment_rate', 'reaction_rate', 'reaction_burst'), 'anti_raid': ('join_rate', 'leave_rate', 'new_account_ratio', 'new_member_activity')}
ALLOWED_ACTIONS = {'warn', 'timeout', 'untimeout', 'kick', 'ban', 'unban', 'softban', 'purge', 'lock', 'unlock', 'lockdown', 'unlockdown'}

def create_router(context: ApiContext) -> APIRouter:
    router = APIRouter()
    auth = ApiDependencies(context.dashboard_repository, context.discord)
    discord = context.discord
    moderation_repository = context.moderation_repository
    guild_settings_repository = context.guild_settings_repository
    manage = auth.manage

    @router.get('/guilds/{guild_id}/moderation/{family}/rules')
    async def rules(request: Request, guild_id: int, family: str) -> dict[str, Any]:
        if family not in FAMILY_TRIGGERS:
            raise api_error(404, 'family_not_found', 'ルール種別が見つかりません。')
        await manage(request, guild_id)
        return {'items': [_serialize_rule_resource_ids(item) for item in moderation_repository.moderation_rules(guild_id, family=family)], 'trigger_types': FAMILY_TRIGGERS[family]}

    @router.get('/guilds/{guild_id}/moderation/{family}/rules/{rule_id}')
    async def rule(request: Request, guild_id: int, family: str, rule_id: int, _access: str=Depends(auth.read)) -> dict[str, Any]:
        value = moderation_repository.moderation_rule(guild_id, rule_id)
        if not value or value['family'] != family:
            raise api_error(404, 'rule_not_found', 'ルールが見つかりません。')
        return _serialize_rule_resource_ids(value)

    def normalized_rule(body: dict[str, Any], family: str) -> dict[str, Any]:
        trigger = str(body.get('trigger_type', ''))
        if family not in FAMILY_TRIGGERS or trigger not in FAMILY_TRIGGERS[family]:
            raise ValueError('trigger_type')
        defaults = default_rule(trigger)
        value = {**defaults, **body, 'family': family, 'trigger_config': {**defaults['trigger_config'], **dict(body.get('trigger_config') or {})}}
        value['event_type'] = str(body.get('event_type') or ('member_join' if trigger in {'join_rate', 'new_account_ratio'} else 'member_remove' if trigger == 'leave_rate' else 'reaction_add' if trigger.startswith('reaction_') else 'message_create'))
        return validate_rule(value)

    @router.post('/guilds/{guild_id}/moderation/{family}/rules', status_code=201, dependencies=[Depends(auth.csrf)])
    async def create_rule(request: Request, guild_id: int, family: str, _access: str=Depends(auth.write)) -> dict[str, Any]:
        try:
            value = normalized_rule(await request.json(), family)
            value['priority'] = moderation_repository.next_moderation_rule_priority(guild_id, family)
            return _serialize_rule_resource_ids(moderation_repository.save_moderation_rule(guild_id, value))
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'rule_invalid', str(exc) or 'ルールを確認してください。') from exc

    @router.put('/guilds/{guild_id}/moderation/{family}/rules/order', dependencies=[Depends(auth.csrf)])
    async def reorder_rules(request: Request, guild_id: int, family: str, _access: str=Depends(auth.write)) -> dict[str, Any]:
        if family not in FAMILY_TRIGGERS:
            raise api_error(404, 'family_not_found', 'ルール種別が見つかりません。')
        try:
            body = await request.json()
            items = body.get('items')
            if not isinstance(items, list):
                raise ValueError('items')
            return {'items': [_serialize_rule_resource_ids(item) for item in moderation_repository.reorder_moderation_rules(guild_id, family, items)]}
        except RuntimeError as exc:
            raise revision_conflict('別の管理者がルール一覧を更新しました。再読み込みしてください。') from exc
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'rule_order_invalid', 'ルールの順序を再読み込みして、もう一度保存してください。') from exc

    @router.put('/guilds/{guild_id}/moderation/{family}/rules/{rule_id}', dependencies=[Depends(auth.csrf)])
    async def update_rule(request: Request, guild_id: int, family: str, rule_id: int, _access: str=Depends(auth.write)) -> dict[str, Any]:
        body, current = (await request.json(), moderation_repository.moderation_rule(guild_id, rule_id))
        if not current or current['family'] != family:
            raise api_error(404, 'rule_not_found', 'ルールが見つかりません。')
        check_revision(body.get('revision'), int(current['revision']), '別の管理者がルールを更新しました。再読み込みしてください。')
        try:
            value = normalized_rule(body, family)
            value['priority'] = current['priority']
            return _serialize_rule_resource_ids(moderation_repository.save_moderation_rule(guild_id, value, rule_id))
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'rule_invalid', str(exc) or 'ルールを確認してください。') from exc

    @router.delete('/guilds/{guild_id}/moderation/{family}/rules/{rule_id}', status_code=204, dependencies=[Depends(auth.csrf)])
    async def delete_rule(request: Request, guild_id: int, family: str, rule_id: int, if_match: str | None=Header(default=None), _access: str=Depends(auth.write)) -> None:
        current = moderation_repository.moderation_rule(guild_id, rule_id)
        if not current or current['family'] != family:
            raise api_error(404, 'rule_not_found', 'ルールが見つかりません。')
        check_revision(if_match, int(current['revision']), '別の管理者がルールを更新しました。')
        moderation_repository.delete_moderation_rule(guild_id, rule_id)

    @router.post('/guilds/{guild_id}/moderation/{family}/rules/{rule_id}/duplicate', status_code=201, dependencies=[Depends(auth.csrf)])
    async def duplicate_rule(request: Request, guild_id: int, family: str, rule_id: int, _access: str=Depends(auth.write)) -> dict[str, Any]:
        current = moderation_repository.moderation_rule(guild_id, rule_id)
        if not current or current['family'] != family:
            raise api_error(404, 'rule_not_found', 'ルールが見つかりません。')
        copy = {key: value for key, value in current.items() if key not in {'id', 'guild_id', 'revision', 'created_at', 'updated_at'}}
        copy.update({'name': f"{current['name']} (コピー)"[:100], 'enabled': False, 'priority': moderation_repository.next_moderation_rule_priority(guild_id, family)})
        return _serialize_rule_resource_ids(moderation_repository.save_moderation_rule(guild_id, validate_rule(copy)))

    @router.post('/guilds/{guild_id}/moderation/{family}/preview', dependencies=[Depends(auth.csrf)])
    async def preview(request: Request, guild_id: int, family: str, _access: str=Depends(auth.read)) -> dict[str, Any]:
        body = await request.json()
        try:
            value = normalized_rule(body.get('rule', {}), family)
            test = body.get('input', {})
            context = MessageContext(guild_id, 1, int(test.get('channel_id') or 1), content=str(test.get('content', ''))[:4000], mention_count=max(0, min(int(test.get('mentions', 0)), 100)), attachment_count=max(0, min(int(test.get('attachments', 0)), 20)), sticker_count=max(0, min(int(test.get('stickers', 0)), 100)), event_type=value['event_type'])
            engine, matches = (AutoModEngine(), [])
            repeats = int(value['trigger_config'].get('limit', 1)) if value['trigger_type'].endswith('rate') or value['trigger_type'] in {'duplicate', 'reaction_burst', 'new_account_ratio', 'emoji_sticker_rate'} else 1
            for _ in range(max(1, min(repeats, 100))):
                matches = await engine.evaluate(context, [{**value, 'id': 1}])
            return {'matched': bool(matches), 'reason': matches[0].reason if matches else '一致しませんでした。', 'trace': ['actor', 'global_exemptions', 'family_exemptions', 'rule_exemptions', 'conditions', 'trigger']}
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'preview_invalid', 'ルールまたはテスト入力を確認してください。') from exc

    @router.get('/guilds/{guild_id}/moderation/events')
    async def events(request: Request, guild_id: int, family: str | None=None, user_id: int | None=None, limit: int=50, _access: str=Depends(auth.read)) -> dict[str, Any]:
        return {'items': moderation_repository.recent_moderation_events(guild_id, family=family, user_id=user_id, limit=limit)}

    @router.get('/guilds/{guild_id}/moderation/infractions/{user_id}')
    async def infractions(request: Request, guild_id: int, user_id: int, _access: str=Depends(auth.read)) -> dict[str, Any]:
        return {'user_id': str(user_id), 'active_points': moderation_repository.active_points(guild_id, user_id), 'cases': moderation_repository.recent_cases(guild_id, user_id, 100)}

    @router.post('/guilds/{guild_id}/moderation/actions', status_code=202, dependencies=[Depends(auth.csrf)])
    async def action(request: Request, guild_id: int, access: str=Depends(auth.write)) -> dict[str, Any]:
        user, body = (await discord.current_user(access, use_cache=False), await request.json())
        action_name, reason = (str(body.get('action', '')), str(body.get('reason', '')).strip()[:500])
        if action_name not in ALLOWED_ACTIONS or not reason or body.get('confirmed') is not True:
            raise api_error(422, 'action_invalid', '処置、理由、確認内容を確認してください。')
        if not guild_settings_repository.module_enabled(guild_id, 'moderation'):
            raise api_error(409, 'moderation_disabled', 'Moderationを有効にしてから処置を実行してください。')
        try:
            target_user_id = int(body['target_user_id']) if body.get('target_user_id') else None
            channel_id = int(body['channel_id']) if body.get('channel_id') else None
            channels, _, bot_permissions = await discord.guild_resources(guild_id, use_cache=False)
            guild_channel_ids = {int(item['id']) for item in channels}
            text_channel_ids = {int(item['id']) for item in channels if int(item['type']) in {0, 5, 15}}
            target_actions = {'warn', 'timeout', 'untimeout', 'kick', 'ban', 'unban', 'softban'}
            channel_actions = {'purge', 'lock', 'unlock'}
            required_permissions = {'timeout': 'moderate_members', 'untimeout': 'moderate_members', 'kick': 'kick_members', 'ban': 'ban_members', 'unban': 'ban_members', 'softban': 'ban_members', 'purge': 'manage_messages', 'lock': 'manage_channels', 'unlock': 'manage_channels', 'lockdown': 'manage_channels', 'unlockdown': 'manage_channels'}
            if action_name in target_actions and (target_user_id is None or target_user_id <= 0):
                raise ValueError('target user is required')
            if action_name in channel_actions and (channel_id is None or channel_id not in text_channel_ids):
                raise ValueError('a text channel from this server is required')
            if channel_id is not None and channel_id not in guild_channel_ids:
                raise ValueError('channel belongs to another server')
            confirmation = str(body.get('confirmation', '')).strip()
            expected = str(guild_id) if action_name == 'lockdown' else str(target_user_id or '')
            if action_name in {'ban', 'softban', 'lockdown'} and confirmation != expected:
                raise ValueError('typed confirmation does not match')
            permission = required_permissions.get(action_name)
            if permission and (not (bot_permissions & ADMINISTRATOR or bot_permissions & PERMISSION_BITS[permission])):
                raise PermissionError(f'missing {permission}')
        except (TypeError, ValueError, PermissionError) as exc:
            raise api_error(422, 'action_invalid', '対象、チャンネル、Bot権限、確認入力を確認してください。') from exc
        request_id = moderation_repository.enqueue_moderation_action(guild_id, int(user['id']), action_name, target_user_id=target_user_id, channel_id=channel_id, reason=reason, options={'duration_minutes': max(1, min(int(body.get('duration_minutes', 10)), 525600)), 'count': max(1, min(int(body.get('count', 10)), 100))}, dedupe_key=f'dashboard-v2:{guild_id}:{secrets.token_urlsafe(16)}')
        return {'request_id': request_id, 'status': 'queued'}
    return router
