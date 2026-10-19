"""Suggestions API routes."""
from __future__ import annotations
from dashboard.api.errors import api_error, revision_conflict
from fastapi import Depends
from typing import Any
from fastapi import APIRouter, Request
from dashboard.discord_api import ADMINISTRATOR, PERMISSION_BITS
from features.registry import get_feature
from suggestions import SuggestionService, SuggestionValidationError, normalize_settings as normalize_suggestion_settings
from dashboard.api.context import ApiContext
from dashboard.api.route import ApiRoute, ERROR_RESPONSES
from dashboard.api import schemas
from dashboard.api.schemas import inputs
from dashboard.api.body import read_body, request_schema
from dashboard.api.resources import GuildResources
from dashboard.api.dependencies import ApiDependencies
from dashboard.api.features import FeaturePresenter

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
            required = list(get_feature('suggestions').required_bot_permissions)
            if value.get('discussion_enabled'):
                required.extend(['create_public_threads', 'send_messages_in_threads', 'read_message_history'])
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
    async def suggestion_items(request: Request, guild_id: int, before: int | None=None, limit: int=50, category: str | None=None, tag: str | None=None, status: str | None=None, _access: str=Depends(auth.read)) -> dict[str, Any]:
        try:
            items = suggestion_repository.list(guild_id, before=before, limit=limit,category=category,tag=tag,status=status)
        except ValueError as exc:
            raise api_error(422,'suggestion_filter_invalid','状態のフィルターを確認してください。') from exc
        for item in items:
            for key in ('author_id', 'channel_id', 'message_id', 'reviewer_id', 'discussion_thread_id'):
                if item.get(key) is not None:
                    item[key] = str(item[key])
        return {'items': items}

    def roadmap_wire(item):
        if item is None:raise api_error(404,'suggestion_not_found','保存期限内の提案が見つかりません。')
        for key in ('guild_id','author_id','channel_id','message_id','reviewer_id','discussion_thread_id'):
            if item.get(key) is not None:item[key]=str(item[key])
        return item

    def roadmap_error(exc):
        if isinstance(exc,LookupError):return api_error(404,'suggestion_not_found','保存期限内の同じサーバーの提案を指定してください。')
        if isinstance(exc,PermissionError):return api_error(403,'suggestion_forbidden','この操作は現在許可されていません。')
        if isinstance(exc,RuntimeError):return revision_conflict('提案が更新されたか既に統合されています。再読み込みしてください。')
        return api_error(422,'suggestion_roadmap_invalid',str(exc) if isinstance(exc,SuggestionValidationError) else 'カテゴリー、タグ、統合先と理由を確認してください。')

    @router.get('/guilds/{guild_id}/suggestions/items/{suggestion_id}',response_model=schemas.SuggestionItem,response_model_exclude_unset=True)
    async def suggestion_detail(request:Request,guild_id:int,suggestion_id:int,_access=Depends(auth.read)):
        return roadmap_wire(suggestion_repository.get(guild_id,suggestion_id))

    @router.post('/guilds/{guild_id}/suggestions/items/{suggestion_id}/labels',dependencies=[Depends(auth.csrf)],response_model=schemas.SuggestionItem,response_model_exclude_unset=True,openapi_extra=request_schema(schemas.SuggestionLabelsInput))
    async def labels(request:Request,guild_id:int,suggestion_id:int,_access=Depends(auth.write)):
        body=await read_body(request,schemas.SuggestionLabelsInput)
        actor=await discord.current_user(auth.token(request))
        try:return roadmap_wire(suggestion_repository.set_labels(guild_id,suggestion_id,int(actor['id']),body.get('category',''),body.get('tags',[]),body['revision']))
        except (LookupError,PermissionError,RuntimeError,ValueError) as exc:raise roadmap_error(exc) from exc

    @router.post('/guilds/{guild_id}/suggestions/items/{suggestion_id}/merge',dependencies=[Depends(auth.csrf)],response_model=schemas.SuggestionItem,response_model_exclude_unset=True,openapi_extra=request_schema(schemas.SuggestionMergeInput))
    async def merge(request:Request,guild_id:int,suggestion_id:int,_access=Depends(auth.write)):
        body=await read_body(request,schemas.SuggestionMergeInput)
        actor=await discord.current_user(auth.token(request))
        try:return roadmap_wire(suggestion_repository.merge(guild_id,suggestion_id,body['target_id'],int(actor['id']),body['reason'],body['revision'],body['target_revision']))
        except (LookupError,PermissionError,RuntimeError,ValueError) as exc:raise roadmap_error(exc) from exc

    @router.get('/guilds/{guild_id}/suggestions/items/{suggestion_id}/events', response_model=schemas.Items[schemas.SuggestionEvent], response_model_exclude_unset=True)
    async def suggestion_events(request: Request, guild_id: int, suggestion_id: int, before: int | None=None,
                                limit: int=50, _access: str=Depends(auth.read)) -> dict[str, Any]:
        try:
            items = suggestion_repository.events(guild_id, suggestion_id, before=before, limit=limit)
        except LookupError as exc:
            raise api_error(404, 'suggestion_not_found', '提案が見つかりません。') from exc
        for item in items:
            if item.get('actor_id') is not None:
                item['actor_id'] = str(item['actor_id'])
        return {'items': items}

    @router.post('/guilds/{guild_id}/suggestions/items/{suggestion_id}/review', dependencies=[Depends(auth.csrf)],
        response_model=schemas.SuggestionItem, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.SuggestionReviewInput))
    async def review_suggestion(request: Request, guild_id: int, suggestion_id: int, _access: str=Depends(auth.write)) -> dict[str, Any]:
        body = await read_body(request, inputs.SuggestionReviewInput)
        if not guild_settings_repository.get_module(guild_id, 'suggestions')['enabled']:
            raise api_error(409, 'suggestions_disabled', 'Suggestionsは無効です。')
        reason = body['reason'].strip()
        if not reason:
            raise api_error(422, 'suggestion_reason_required', '審査理由を入力してください。')
        actor = await discord.current_user(auth.token(request))
        try:
            item = SuggestionService(suggestion_repository).review(guild_id, suggestion_id, int(actor['id']), body['status'],
                reason, expected_revision=body['revision'])
        except LookupError as exc:
            raise api_error(404, 'suggestion_not_found', '提案が見つかりません。') from exc
        except RuntimeError as exc:
            raise revision_conflict('提案が更新されています。再読み込みしてください。') from exc
        for key in ('author_id', 'channel_id', 'message_id', 'reviewer_id', 'discussion_thread_id'):
            if item.get(key) is not None:
                item[key] = str(item[key])
        return item
    return router
