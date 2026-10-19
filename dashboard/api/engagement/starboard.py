"""Guild manager board configuration, retained source history and fenced retry."""
from fastapi import APIRouter,Depends,Request
from dashboard.api.dependencies import ApiDependencies
from dashboard.api.route import ApiRoute,ERROR_RESPONSES
from dashboard.api.body import read_body,request_schema
from dashboard.api.errors import api_error,revision_conflict
from dashboard.api.resources import GuildResources
from dashboard.api import schemas
from starboard.models import normalize


def wire(value,key=None):
    if isinstance(value,list):return [str(v) if key in ('source_channel_ids','excluded_channel_ids') else wire(v) for v in value]
    if isinstance(value,dict):return {k:wire(v,k) for k,v in value.items() if k not in ('request_key','config_json','snapshot_json','detail_json')}
    if key in ('guild_id','actor_id','retry_actor_id','channel_id','target_channel_id','source_channel_id','source_message_id','message_id','author_id','parent_channel_id') and value is not None:return str(value)
    return value


def create_router(context):
    router=APIRouter(route_class=ApiRoute,responses=ERROR_RESPONSES)
    auth=ApiDependencies(context.dashboard_repository,context.discord);repo=context.starboard_repository

    def failure(exc):
        if isinstance(exc,LookupError):return api_error(404,'starboard_not_found','保存期限内のBoardまたは配送が見つかりません。')
        if isinstance(exc,PermissionError):return api_error(403,'starboard_disabled','Starboardが無効です。')
        if isinstance(exc,RuntimeError):return revision_conflict('設定や配送状態が更新されています。再取得して確認してください。')
        return api_error(422,'starboard_invalid','投稿元・投稿先・絵文字・閾値・保存日数を確認してください。')

    async def values(guild,body):
        config=normalize(body['config'])
        # An obsolete/deleted channel or emoji must not prevent withdrawal.
        # Enabling always repeats the live Guild/resource checks.
        if not config['enabled']:return config
        resources=await GuildResources.fetch(context.discord,guild,live=True)
        available=resources.channels
        for item in {config['target_channel_id'],*config['source_channel_ids'],*config['excluded_channel_ids']}:
            if item not in available:
                channel=await context.discord.guild_channel(guild,item)
                if not channel:raise ValueError('foreign_or_missing_channel')
                available[item]=channel
            allowed=(0,5,10,11,12) if item==config['target_channel_id'] else (0,5,10,11,12,15,16)
            if int(available[item].get('type',-1)) not in allowed:raise ValueError('channel_type')
        if config['emoji'].startswith('custom:'):
            emojis=await context.discord.guild_emojis(guild,use_cache=False)
            if config['emoji'].split(':')[1] not in {str(item['id']) for item in emojis}:raise ValueError('foreign_emoji')
        return config

    async def actor(request):return int((await context.discord.current_user(auth.token(request)))['id'])

    @router.get('/guilds/{guild_id}/starboard/boards',response_model=schemas.Items[schemas.StarboardItem])
    async def boards(request:Request,guild_id:int,_access=Depends(auth.read)):
        return {'items':wire(repo.boards(guild_id))}

    @router.post('/guilds/{guild_id}/starboard/boards',dependencies=[Depends(auth.csrf)],response_model=schemas.StarboardItem,openapi_extra=request_schema(schemas.StarboardCreateInput))
    async def create(request:Request,guild_id:int,_access=Depends(auth.write)):
        body=await read_body(request,schemas.StarboardCreateInput)
        try:return wire(repo.save_board(guild_id,await actor(request),await values(guild_id,body),request_key=body['request_key']))
        except (ValueError,LookupError,PermissionError,RuntimeError) as exc:raise failure(exc) from exc

    @router.put('/guilds/{guild_id}/starboard/boards/{board_id}',dependencies=[Depends(auth.csrf)],response_model=schemas.StarboardItem,openapi_extra=request_schema(schemas.StarboardEditInput))
    async def edit(request:Request,guild_id:int,board_id:int,_access=Depends(auth.write)):
        body=await read_body(request,schemas.StarboardEditInput)
        try:return wire(repo.save_board(guild_id,await actor(request),await values(guild_id,body),board=board_id,revision=body['revision']))
        except (ValueError,LookupError,PermissionError,RuntimeError) as exc:raise failure(exc) from exc

    @router.get('/guilds/{guild_id}/starboard/boards/{board_id}/entries',response_model=schemas.Items[schemas.HighlightEntry])
    async def entries(request:Request,guild_id:int,board_id:int,before:int|None=None,limit:int=50,_access=Depends(auth.read)):
        try:return {'items':wire(repo.entries(guild_id,board_id,before=before,limit=limit))}
        except LookupError as exc:raise failure(exc) from exc

    @router.get('/guilds/{guild_id}/starboard/boards/{board_id}/history',response_model=schemas.HighlightHistory)
    async def history(request:Request,guild_id:int,board_id:int,_access=Depends(auth.read)):
        try:return wire(repo.delivery_history(guild_id,board_id))
        except LookupError as exc:raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/starboard/boards/{board_id}/delivery/{job_id}/retry',dependencies=[Depends(auth.csrf)],response_model=schemas.HighlightHistory,openapi_extra=request_schema(schemas.StarboardRevisionInput))
    async def retry(request:Request,guild_id:int,board_id:int,job_id:int,_access=Depends(auth.write)):
        body=await read_body(request,schemas.StarboardRevisionInput)
        try:
            repo.retry(guild_id,board_id,job_id,await actor(request),body['revision'])
            return wire(repo.delivery_history(guild_id,board_id))
        except (ValueError,LookupError,PermissionError,RuntimeError) as exc:raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/starboard/boards/{board_id}/source-jobs/{job_id}/retry',dependencies=[Depends(auth.csrf)],response_model=schemas.HighlightHistory,openapi_extra=request_schema(schemas.StarboardRevisionInput))
    async def retry_source(request:Request,guild_id:int,board_id:int,job_id:int,_access=Depends(auth.write)):
        body=await read_body(request,schemas.StarboardRevisionInput)
        try:
            repo.retry_source(guild_id,board_id,job_id,await actor(request),body['revision'])
            return wire(repo.delivery_history(guild_id,board_id))
        except (ValueError,LookupError,PermissionError,RuntimeError) as exc:raise failure(exc) from exc
    return router
