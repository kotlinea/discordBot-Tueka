"""Guild-manager campaign configuration, lifecycle and audited job retry."""
import json
import time
from fastapi import APIRouter, Depends, Request
from dashboard.api.dependencies import ApiDependencies
from dashboard.api.route import ApiRoute, ERROR_RESPONSES
from dashboard.api.body import read_body, request_schema
from dashboard.api.errors import api_error, revision_conflict
from dashboard.api.resources import GuildResources
from dashboard.api import schemas
from giveaways.models import normalize


def wire(value, key=None):
    if isinstance(value, list):
        return [str(v) if key in ('required_role_ids', 'denied_role_ids', 'candidates', 'winners') else wire(v) for v in value]
    if isinstance(value, dict):
        result = {k: wire(v, k) for k, v in value.items() if k not in ('request_key', 'config_json', 'candidates_json', 'winners_json', 'detail_json')}
        for field in ('candidates', 'winners', 'detail'):
            if field + '_json' in value:
                result[field] = wire(json.loads(value[field + '_json']), field)
        return result
    if key in ('guild_id', 'actor_id', 'user_id', 'channel_id', 'message_id') and value is not None:
        return str(value)
    return value


def create_router(context):
    router = APIRouter(route_class=ApiRoute, responses=ERROR_RESPONSES)
    auth = ApiDependencies(context.dashboard_repository, context.discord)
    repo = context.giveaway_repository

    def failure(exc):
        if isinstance(exc, LookupError):
            return api_error(404, 'giveaway_not_found', '保存期限内の受付・処理が見つかりません。')
        if isinstance(exc, PermissionError):
            return api_error(403, 'giveaway_disabled', '参加受付機能が無効です。')
        if isinstance(exc, RuntimeError):
            return revision_conflict('状態が更新されています。再取得して確認してください。')
        return api_error(422, 'giveaway_invalid', '対象・期限・参加条件・理由を確認してください。')

    async def actor(request):
        return int((await context.discord.current_user(auth.token(request)))['id'])

    async def values(guild, raw):
        config = normalize(raw, int(time.time()))
        resources = await GuildResources.fetch(context.discord, guild, live=True)
        channel = resources.channels.get(config['channel_id'])
        if not channel or int(channel.get('type', -1)) not in (0, 5):
            raise ValueError('missing_or_foreign_channel')
        if not set(config['required_role_ids'] + config['denied_role_ids']) <= resources.role_ids:
            raise ValueError('missing_or_foreign_role')
        return config

    @router.get('/guilds/{guild_id}/giveaways', response_model=schemas.Items[schemas.GiveawayItem])
    async def items(request: Request, guild_id: int, before: int | None = None, limit: int = 50, _access=Depends(auth.read)):
        return {'items': wire(repo.items(guild_id, before=before, limit=limit))}

    @router.post('/guilds/{guild_id}/giveaways', dependencies=[Depends(auth.csrf)], response_model=schemas.GiveawayItem, openapi_extra=request_schema(schemas.GiveawayCreateInput))
    async def create(request: Request, guild_id: int, _access=Depends(auth.write)):
        body = await read_body(request, schemas.GiveawayCreateInput)
        try:
            user = await actor(request)
            previous = repo.existing_creation(guild_id, user, body['config'], body['request_key'])
            if previous:
                return wire(previous)
            return wire(repo.create(guild_id, user, await values(guild_id, body['config']), body['request_key']))
        except (ValueError, LookupError, PermissionError, RuntimeError) as exc:
            raise failure(exc) from exc

    @router.get('/guilds/{guild_id}/giveaways/{item_id}', response_model=schemas.GiveawayItem)
    async def item(request: Request, guild_id: int, item_id: int, _access=Depends(auth.read)):
        try:
            return wire(repo.item(guild_id, item_id))
        except LookupError as exc:
            raise failure(exc) from exc

    @router.put('/guilds/{guild_id}/giveaways/{item_id}', dependencies=[Depends(auth.csrf)], response_model=schemas.GiveawayItem, openapi_extra=request_schema(schemas.GiveawayEditInput))
    async def edit(request: Request, guild_id: int, item_id: int, _access=Depends(auth.write)):
        body = await read_body(request, schemas.GiveawayEditInput)
        try:
            return wire(repo.edit(guild_id, item_id, await actor(request), await values(guild_id, body['config']), body['revision']))
        except (ValueError, LookupError, PermissionError, RuntimeError) as exc:
            raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/giveaways/{item_id}/launch', dependencies=[Depends(auth.csrf)], response_model=schemas.GiveawayItem, openapi_extra=request_schema(schemas.GiveawayRevisionInput))
    async def launch(request: Request, guild_id: int, item_id: int, _access=Depends(auth.write)):
        body = await read_body(request, schemas.GiveawayRevisionInput)
        try:
            current = repo.item(guild_id, item_id)
            await values(guild_id, current['config'])
            return wire(repo.launch(guild_id, item_id, await actor(request), body['revision']))
        except (ValueError, LookupError, PermissionError, RuntimeError) as exc:
            raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/giveaways/{item_id}/cancel', dependencies=[Depends(auth.csrf)], response_model=schemas.GiveawayItem, openapi_extra=request_schema(schemas.GiveawayReasonInput))
    async def cancel(request: Request, guild_id: int, item_id: int, _access=Depends(auth.write)):
        body = await read_body(request, schemas.GiveawayReasonInput)
        try:
            return wire(repo.cancel(guild_id, item_id, await actor(request), body['revision'], body['reason']))
        except (ValueError, LookupError, PermissionError, RuntimeError) as exc:
            raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/giveaways/{item_id}/close', dependencies=[Depends(auth.csrf)], response_model=schemas.GiveawayItem, openapi_extra=request_schema(schemas.GiveawayReasonInput))
    async def close(request: Request, guild_id: int, item_id: int, _access=Depends(auth.write)):
        body = await read_body(request, schemas.GiveawayReasonInput)
        try:
            return wire(repo.close(guild_id, item_id, await actor(request), body['revision'], body['reason']))
        except (ValueError, LookupError, PermissionError, RuntimeError) as exc:
            raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/giveaways/{item_id}/reroll', dependencies=[Depends(auth.csrf)], response_model=schemas.GiveawayItem, openapi_extra=request_schema(schemas.GiveawayReasonInput))
    async def reroll(request: Request, guild_id: int, item_id: int, _access=Depends(auth.write)):
        body = await read_body(request, schemas.GiveawayReasonInput)
        try:
            return wire(repo.reroll(guild_id, item_id, await actor(request), body['revision'], body['reason']))
        except (ValueError, LookupError, PermissionError, RuntimeError) as exc:
            raise failure(exc) from exc

    @router.get('/guilds/{guild_id}/giveaways/{item_id}/history', response_model=schemas.GiveawayHistory)
    async def history(request: Request, guild_id: int, item_id: int, _access=Depends(auth.read)):
        try:
            return wire(repo.history(guild_id, item_id))
        except LookupError as exc:
            raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/giveaways/{item_id}/jobs/{job_id}/retry', dependencies=[Depends(auth.csrf)], response_model=schemas.GiveawayHistory, openapi_extra=request_schema(schemas.GiveawayRevisionInput))
    async def retry(request: Request, guild_id: int, item_id: int, job_id: int, draw: bool = False, _access=Depends(auth.write)):
        body = await read_body(request, schemas.GiveawayRevisionInput)
        try:
            repo.retry(guild_id, item_id, await actor(request), body['revision'], job_id, draw=draw)
            return wire(repo.history(guild_id, item_id))
        except (ValueError, LookupError, PermissionError, RuntimeError) as exc:
            raise failure(exc) from exc
    return router
