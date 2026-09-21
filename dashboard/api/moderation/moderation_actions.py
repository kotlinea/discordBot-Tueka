"""Moderation API routes."""
from __future__ import annotations
from dashboard.api.errors import api_error, revision_conflict, check_revision
from fastapi import Depends
import secrets
from typing import Any
from fastapi import APIRouter, Header, Request
from moderation import AutoModEngine, MessageContext, default_rule, validate_rule
from dashboard.discord_api import ADMINISTRATOR, PERMISSION_BITS
from dashboard.api.context import ApiContext
from dashboard.api.route import ApiRoute, ERROR_RESPONSES
from dashboard.api import schemas
from dashboard.api.schemas import inputs
from dashboard.api.body import read_body, request_schema
from dashboard.api.dependencies import ApiDependencies
from dashboard.api.serialization import _serialize_rule_resource_ids
ALLOWED_ACTIONS = {'warn', 'timeout', 'untimeout', 'kick', 'ban', 'unban', 'softban', 'purge', 'lock', 'unlock', 'lockdown', 'unlockdown'}

def create_router(context: ApiContext) -> APIRouter:
    router = APIRouter(route_class=ApiRoute, responses=ERROR_RESPONSES)
    auth = ApiDependencies(context.dashboard_repository, context.discord)
    discord = context.discord
    moderation_repository = context.moderation_repository
    guild_settings_repository = context.guild_settings_repository
    manage = auth.manage

    @router.post('/guilds/{guild_id}/moderation/actions', status_code=202, dependencies=[Depends(auth.csrf)], response_model=schemas.ActionResponse, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.ModerationActionInput))
    async def action(request: Request, guild_id: int, access: str=Depends(auth.write)) -> dict[str, Any]:
        user, body = (await discord.current_user(access, use_cache=False), await read_body(request, inputs.ModerationActionInput))
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
