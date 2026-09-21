"""Modules API routes."""
from __future__ import annotations
from .errors import api_error, revision_conflict
from fastapi import Depends
from typing import Any
from fastapi import APIRouter, Request
from dashboard.discord_api import ADMINISTRATOR, PERMISSION_BITS
from features.registry import get_feature
from .context import ApiContext
from .route import ApiRoute, ERROR_RESPONSES
from . import schemas
from .schemas import inputs
from .body import read_body, request_schema
from .resources import GuildResources
from .dependencies import ApiDependencies
from .features import FeaturePresenter
from .serialization import _serialize_resource_ids
from .serialization import _normalize_resource_ids
from .resources import validate_resource_ids

def create_router(context: ApiContext) -> APIRouter:
    router = APIRouter(route_class=ApiRoute, responses=ERROR_RESPONSES)
    auth = ApiDependencies(context.dashboard_repository, context.discord)
    discord = context.discord
    feature_payload = FeaturePresenter(context).feature_payload

    @router.get('/guilds/{guild_id}/modules/{module_id}', response_model=schemas.Feature, response_model_exclude_unset=True)
    async def module(request: Request, guild_id: int, module_id: str, _access: str=Depends(auth.read)) -> dict[str, Any]:
        try:
            feature = get_feature(module_id)
        except ValueError as exc:
            raise api_error(404, 'module_not_found', '機能が見つかりません。') from exc
        _, _, permissions = await discord.guild_resources(guild_id)
        return feature_payload(guild_id, feature, permissions)

    @router.put('/guilds/{guild_id}/modules/{module_id}', dependencies=[Depends(auth.csrf)], response_model=schemas.ModuleValue, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.ModuleInput))
    async def save_module(request: Request, guild_id: int, module_id: str, _access: str=Depends(auth.write)) -> dict[str, Any]:
        if module_id in {'tickets', 'reaction_roles'}:
            raise api_error(404, 'module_not_found', '機能専用の設定APIを使用してください。')
        try:
            feature = get_feature(module_id)
            body = await read_body(request, inputs.ModuleInput)
            snapshot = await GuildResources.fetch(discord, guild_id)
            permissions = snapshot.permissions
            values = body.get('settings', {})
            if not isinstance(values, dict):
                raise ValueError('settings')
            validate_resource_ids(values, snapshot.channel_ids(), snapshot.role_ids)
            if bool(body.get('enabled')):
                required = set(feature.required_bot_permissions)
                if any((not values.get(field) for field in feature.required_fields)):
                    raise ValueError('required_settings')
                if module_id == 'audit_log' and values.get('log_member'):
                    required.add('view_audit_log')
                if module_id == 'leveling':
                    if values.get('voice_enabled') and (not values.get('voice_notification_channel_id')):
                        raise ValueError('voice_notification_channel_id')
                    if values.get('text_role_rewards') or values.get('voice_role_rewards'):
                        required.add('manage_roles')
                if not permissions & ADMINISTRATOR and any((not permissions & PERMISSION_BITS[name] for name in required)):
                    raise ValueError('missing_permissions')
            access = context.feature_settings[module_id]
            access.validate(bool(body.get('enabled')), values)
            saved = access.save(guild_id, enabled=bool(body.get('enabled')), settings=_normalize_resource_ids(values), expected_revision=int(body['revision']) if body.get('revision') is not None else None)
            return {**saved, 'settings': _serialize_resource_ids(saved['settings'])}
        except RuntimeError as exc:
            raise revision_conflict('別の管理者が設定を更新しました。再読み込みしてください。') from exc
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'module_invalid', 'サーバー内のチャンネル、ロール、設定値を確認してください。') from exc
    return router
