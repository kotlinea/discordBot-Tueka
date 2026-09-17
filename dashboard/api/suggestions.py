"""Suggestions API routes."""
from __future__ import annotations
from .errors import api_error, revision_conflict
from fastapi import Depends
from typing import Any
from fastapi import APIRouter, Request
from dashboard.discord_api import ADMINISTRATOR, PERMISSION_BITS
from feature_registry import get_feature
from suggestions import SuggestionValidationError, normalize_settings as normalize_suggestion_settings
from .context import ApiContext
from .route import ApiRoute, ERROR_RESPONSES
from . import schemas
from .schemas import inputs
from .body import read_body, request_schema
from .resources import GuildResources
from .dependencies import ApiDependencies
from .features import FeaturePresenter

def create_router(context: ApiContext) -> APIRouter:
    router = APIRouter(route_class=ApiRoute, responses=ERROR_RESPONSES)
    auth = ApiDependencies(context.dashboard_repository, context.discord)
    discord = context.discord
    guild_settings_repository = context.guild_settings_repository
    suggestion_repository = context.suggestion_repository
    resources = auth.resources
    feature_payload = FeaturePresenter(context).feature_payload

    @router.get('/guilds/{guild_id}/suggestions/settings', response_model=schemas.SuggestionFeature, response_model_exclude_unset=True)
    async def suggestion_settings(request: Request, guild_id: int) -> dict[str, Any]:
        _, _, permissions = await resources(request, guild_id)
        return feature_payload(guild_id, get_feature('suggestions'), permissions)

    @router.put('/guilds/{guild_id}/suggestions/settings', dependencies=[Depends(auth.csrf)], response_model=schemas.SuggestionFeature, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.SuggestionInput))
    async def save_suggestion_settings(request: Request, guild_id: int, _access: str=Depends(auth.write)) -> dict[str, Any]:
        body = await read_body(request, inputs.SuggestionInput)
        try:
            value = normalize_suggestion_settings(dict(body.get('settings') or {}))
            enabled = bool(body.get('enabled', False))
            if body.get('revision') is None:
                raise SuggestionValidationError('revision', '画面を再読み込みして、もう一度保存してください。')
            snapshot = await GuildResources.fetch(discord, guild_id)
            permissions = snapshot.permissions
            text_channels = snapshot.channel_ids(0)
            role_ids = snapshot.role_ids
            if (enabled or value['channel_id'] is not None) and value['channel_id'] not in text_channels:
                raise SuggestionValidationError('channel_id', '提案の投稿先を選択してください。')
            if value['log_channel_id'] is not None and value['log_channel_id'] not in text_channels:
                raise SuggestionValidationError('log_channel_id', 'ログチャンネルを選択してください。')
            if set(value['review_role_ids']) - role_ids:
                raise SuggestionValidationError('review_role_ids', 'このサーバーに存在するロールを選択してください。')
            required = get_feature('suggestions').required_bot_permissions
            missing = [] if permissions & ADMINISTRATOR else [name for name in required if not permissions & PERMISSION_BITS[name]]
            if enabled and missing:
                raise SuggestionValidationError('permissions', f"Bot権限が不足しています: {', '.join(missing)}")
            saved = guild_settings_repository.set_module(guild_id, 'suggestions', enabled=enabled, settings=value, expected_revision=int(body['revision']) if body.get('revision') is not None else None)
        except SuggestionValidationError as exc:
            raise api_error(422, 'suggestions_invalid', str(exc), fields=[{'path': exc.path, 'message': str(exc)}]) from exc
        except RuntimeError as exc:
            raise revision_conflict('設定が別の画面で更新されました。再読み込みしてください。') from exc
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'suggestions_invalid', 'Suggestions設定を確認してください。') from exc
        return feature_payload(guild_id, get_feature('suggestions'), permissions)

    @router.get('/guilds/{guild_id}/suggestions/items', response_model=schemas.Items[schemas.SuggestionItem], response_model_exclude_unset=True)
    async def suggestion_items(request: Request, guild_id: int, before: int | None=None, limit: int=50, _access: str=Depends(auth.read)) -> dict[str, Any]:
        items = suggestion_repository.list(guild_id, before=before, limit=limit)
        for item in items:
            for key in ('author_id', 'channel_id', 'message_id', 'reviewer_id'):
                if item.get(key) is not None:
                    item[key] = str(item[key])
        return {'items': items}
    return router
