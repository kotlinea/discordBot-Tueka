"""Manager-only schedule creation, revision editing, cancellation and retry."""
import json
from fastapi import APIRouter, Depends, Request
from dashboard.api.dependencies import ApiDependencies
from dashboard.api.route import ApiRoute, ERROR_RESPONSES
from dashboard.api.body import read_body, request_schema
from dashboard.api.errors import api_error, revision_conflict
from dashboard.api.resources import GuildResources
from dashboard.api import schemas


def wire(row):
    if isinstance(row,list):
        return [wire(item) for item in row]
    if not isinstance(row,dict):
        return row
    result = {key:str(value) if key in ('guild_id','actor_id','channel_id','discord_receipt_id') and value is not None else wire(value)
              for key,value in row.items() if key not in ('request_key','payload_json','interval_seconds')}
    if 'payload_json' in row:
        payload = json.loads(row['payload_json'])
        if payload.get('channel_id') is not None:
            payload['channel_id'] = str(payload['channel_id'])
        result['payload'] = payload
    return result


def create_router(context):
    router = APIRouter(route_class=ApiRoute,responses=ERROR_RESPONSES)
    auth = ApiDependencies(context.dashboard_repository,context.discord)
    repo = context.schedule_repository

    def failure(exc):
        if isinstance(exc,LookupError):
            return api_error(404,'schedule_not_found','保存期限内の予約が見つかりません。')
        if isinstance(exc,PermissionError):
            return api_error(403,'schedule_disabled','予約機能が無効です。')
        if isinstance(exc,RuntimeError):
            return revision_conflict('状態が更新されたか配送が開始されています。履歴を確認してください。')
        return api_error(422,'schedule_invalid','時刻、投稿先、繰り返し回数、イベントの開始と終了を確認してください。')

    async def actor(request):
        return int((await context.discord.current_user(auth.token(request)))['id'])

    async def payload(guild, body):
        values = dict(body['payload'])
        if values.get('channel_id') is not None:
            text = values['channel_id']
            if not isinstance(text,str) or not text.isascii() or not text.isdecimal():
                raise ValueError('channel_id')
            values['channel_id'] = int(text)
        if values['kind'] == 'message':
            snapshot = await GuildResources.fetch(context.discord,guild,live=True)
            if values.get('channel_id') not in snapshot.channel_ids(0):
                raise ValueError('channel_id')
        return values

    @router.get('/guilds/{guild_id}/schedules/items',response_model=schemas.Items[schemas.ScheduleItem])
    async def items(request:Request,guild_id:int,before:int|None=None,limit:int=50,_access=Depends(auth.read)):
        return {'items':wire(repo.items(guild_id,before=before,limit=limit))}

    @router.get('/guilds/{guild_id}/schedules/items/{item_id}/history',response_model=schemas.ScheduleHistory)
    async def history(request:Request,guild_id:int,item_id:int,_access=Depends(auth.read)):
        try:
            return wire(repo.history(guild_id,item_id))
        except LookupError as exc:
            raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/schedules/items',dependencies=[Depends(auth.csrf)],response_model=schemas.ScheduleItem,openapi_extra=request_schema(schemas.ScheduleCreateInput))
    async def create(request:Request,guild_id:int,_access=Depends(auth.write)):
        body = await read_body(request,schemas.ScheduleCreateInput)
        try:
            return wire(repo.create(guild_id,await actor(request),await payload(guild_id,body),body['request_key']))
        except (ValueError,LookupError,PermissionError,RuntimeError) as exc:
            raise failure(exc) from exc

    @router.put('/guilds/{guild_id}/schedules/items/{item_id}',dependencies=[Depends(auth.csrf)],response_model=schemas.ScheduleItem,openapi_extra=request_schema(schemas.ScheduleEditInput))
    async def edit(request:Request,guild_id:int,item_id:int,_access=Depends(auth.write)):
        body = await read_body(request,schemas.ScheduleEditInput)
        try:
            return wire(repo.reschedule(guild_id,item_id,await actor(request),await payload(guild_id,body),body['revision']))
        except (ValueError,LookupError,PermissionError,RuntimeError) as exc:
            raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/schedules/items/{item_id}/cancel',dependencies=[Depends(auth.csrf)],response_model=schemas.ScheduleItem,openapi_extra=request_schema(schemas.ScheduleRevisionInput))
    async def cancel(request:Request,guild_id:int,item_id:int,_access=Depends(auth.write)):
        body = await read_body(request,schemas.ScheduleRevisionInput)
        try:
            return wire(repo.cancel(guild_id,item_id,await actor(request),body['revision']))
        except (ValueError,LookupError,PermissionError,RuntimeError) as exc:
            raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/schedules/items/{item_id}/delivery/{job_id}/retry',dependencies=[Depends(auth.csrf)],response_model=schemas.ScheduleItem,openapi_extra=request_schema(schemas.ScheduleRevisionInput))
    async def retry(request:Request,guild_id:int,item_id:int,job_id:int,_access=Depends(auth.write)):
        body = await read_body(request,schemas.ScheduleRevisionInput)
        try:
            repo.retry(guild_id,item_id,job_id,await actor(request),body['revision'])
            return wire(repo.item(guild_id,item_id))
        except (ValueError,LookupError,PermissionError,RuntimeError) as exc:
            raise failure(exc) from exc
    return router
