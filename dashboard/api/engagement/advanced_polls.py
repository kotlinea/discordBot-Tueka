"""Guild-scoped advanced poll API, live authorization and privacy projection."""
from fastapi import APIRouter, Request, Depends, Response
from dashboard.api.dependencies import ApiDependencies
from dashboard.api.route import ApiRoute, ERROR_RESPONSES
from dashboard.api.body import read_body, request_schema
from dashboard.api.errors import api_error
from dashboard.api.resources import GuildResources
from dashboard.api import schemas
from engagement.polls.models import PollError, disclose, ids
from engagement.polls.service import Actor, PollService
import re


def wire(value):
    if isinstance(value,list): return [wire(item) for item in value]
    if not isinstance(value,dict): return value
    return {key:str(item) if key in ('guild_id','channel_id','message_id','actor_id','discord_receipt_id') and item is not None else wire(item) for key,item in value.items()}


def create_access(context):
    service=PollService(context.poll_repository)
    def check(guild,user,member,metadata):
        manager=bool(metadata.get('owner') or int(metadata.get('permissions',0)) & (0x8 | 0x20))
        return bool(service.permissions(Actor(guild,user,(str(guild),*member.get('roles',[])),manager=manager)))
    return check


def create_router(context):
    router=APIRouter(route_class=ApiRoute,responses=ERROR_RESPONSES)
    auth=ApiDependencies(context.dashboard_repository,context.discord)
    repo=context.poll_repository
    service=PollService(repo)

    async def actor(request:Request,guild_id:int):
        token=auth.token(request)
        user=await context.discord.current_user(token)
        member=await context.discord.guild_member(guild_id,int(user['id']),use_cache=False)
        if not member: raise api_error(403,'guild_forbidden','このサーバーにはアクセスできません。')
        manager=await context.discord.can_manage(token,guild_id,use_cache=False)
        if not manager:
            metadata=next((row for row in await context.discord.user_guilds(token) if str(row['id'])==str(guild_id)),{})
            manager=bool(metadata.get('owner') or int(metadata.get('permissions',0)) & (0x8 | 0x20))
        return Actor(guild_id,int(user['id']),(str(guild_id),*member.get('roles',[])),manager=manager,bot=bool(user.get('bot')))

    def failure(exc):
        status={'not_found':404,'forbidden':403,'disabled':403,'conflict':409,'privacy_expansion':409,'ballot_locked':409,'delivery_uncertain':409}.get(exc.code,422)
        return api_error(status,'poll_'+exc.code,'投票の入力、権限、現在の状態を確認してください。')

    async def validate_resources(guild,channel,config=None):
        resources=await GuildResources.fetch(context.discord,guild,live=True,assignable_roles=False)
        try: channel=int(ids([channel])[0])
        except (PollError,TypeError):raise PollError('invalid') from None
        if channel not in resources.channel_ids(0,5):raise PollError('invalid')
        if config:
            roles=ids(config.get('allowed_roles',[]))+ids(config.get('denied_roles',[]))
            if any(int(role) not in resources.role_ids for role in roles):raise PollError('invalid')
            custom=[int(match[1]) for value in (config.get('emojis') or []) if (match:=re.fullmatch(r'<a?:[A-Za-z0-9_]{2,32}:(\d{1,20})>',value))]
            if custom:
                available={int(emoji['id']) for emoji in await context.discord.guild_emojis(guild,use_cache=False)}
                if any(emoji not in available for emoji in custom):raise PollError('invalid')
        return channel

    @router.get('/guilds/{guild_id}/polls/capabilities',response_model=schemas.PollCapabilities)
    async def capabilities(request:Request,guild_id:int,a=Depends(actor)):
        return {'permissions':sorted(service.permissions(a)),'enabled':repo.settings.module_enabled(guild_id,'advanced_polls')}

    @router.get('/guilds/{guild_id}/polls/resources',response_model=schemas.Resources)
    async def resources(request:Request,guild_id:int,a=Depends(actor)):
        try:
            if not service.permissions(a):raise PollError('forbidden')
            channels,roles,permissions=await context.discord.guild_resources(guild_id,use_cache=False,assignable_roles=False)
            return {'channels':channels,'roles':roles,'bot_permissions':str(permissions)}
        except PollError as exc:raise failure(exc) from exc

    @router.get('/guilds/{guild_id}/polls/items',response_model=schemas.Items[schemas.PollItem],response_model_exclude_none=True)
    async def items(request:Request,guild_id:int,before:int|None=None,a=Depends(actor)):
        try:
            service.require(a,'view')
            return {'items':[wire(service.read(a,item['id'],management=True)) for item in repo.items(guild_id,before=before)]}
        except PollError as exc:raise failure(exc) from exc

    @router.get('/guilds/{guild_id}/polls/items/{poll_id}',response_model=schemas.PollItem,response_model_exclude_none=True)
    async def item(request:Request,guild_id:int,poll_id:int,a=Depends(actor)):
        try:return wire(service.read(a,poll_id,management=True))
        except PollError as exc:raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/polls/items',dependencies=[Depends(auth.csrf)],response_model=schemas.PollItem,response_model_exclude_none=True,openapi_extra=request_schema(schemas.PollCreateInput))
    async def create(request:Request,guild_id:int,a=Depends(actor)):
        body=await read_body(request,schemas.PollCreateInput)
        try:
            service.require(a,'manage')
            channel=await validate_resources(guild_id,body['channel_id'],body['config'])
            row=service.create(a,channel,body['config'],body['request_key'],**{key:body.get(key) for key in ('scheduled_at','duration_seconds','closes_at')})
            return wire(service.read(a,row['id'],management=True))
        except PollError as exc:raise failure(exc) from exc

    @router.put('/guilds/{guild_id}/polls/items/{poll_id}',dependencies=[Depends(auth.csrf)],response_model=schemas.PollItem,response_model_exclude_none=True,openapi_extra=request_schema(schemas.PollEditInput))
    async def edit(request:Request,guild_id:int,poll_id:int,a=Depends(actor)):
        body=await read_body(request,schemas.PollEditInput)
        try:
            service.require(a,'manage')
            current=repo.get(guild_id,poll_id)
            await validate_resources(guild_id,current['channel_id'],body['config'])
            timing={key:body[key] for key in ('closes_at','scheduled_at','duration_seconds') if key in body}
            service.edit(a,poll_id,body['config'],body['revision'],**timing)
            return wire(service.read(a,poll_id,management=True))
        except PollError as exc:raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/polls/items/{poll_id}/actions',dependencies=[Depends(auth.csrf)],response_model=schemas.PollItem,response_model_exclude_none=True,openapi_extra=request_schema(schemas.PollActionInput))
    async def action(request:Request,guild_id:int,poll_id:int,a=Depends(actor)):
        body=await read_body(request,schemas.PollActionInput)
        try:
            service.require(a,'manage')
            current=repo.get(guild_id,poll_id)
            if current['revision']!=body['revision']:raise PollError('conflict')
            kind=body['action']
            if kind in ('launch','move'):
                channel=await validate_resources(guild_id,body.get('channel_id') or current['channel_id'],current['config'])
                row=repo.launch(guild_id,poll_id,a.user_id,body['revision'],channel=channel if kind=='move' else None,principal=a)
            elif kind=='copy':
                row=service.create(a,current['channel_id'],current['config'],body.get('request_key'))
            else:row=service.transition(a,poll_id,kind,body['revision'],closes_at=body.get('closes_at'))
            return wire(service.read(a,row['id'],management=True))
        except PollError as exc:raise failure(exc) from exc

    @router.get('/guilds/{guild_id}/polls/items/{poll_id}/history',response_model=schemas.PollHistory)
    async def history(request:Request,guild_id:int,poll_id:int,a=Depends(actor)):
        try:
            service.require(a,'view')
            return wire({'events':repo.history(guild_id,poll_id),'delivery':repo.delivery_history(guild_id,poll_id)})
        except PollError as exc:raise failure(exc) from exc

    @router.get('/guilds/{guild_id}/polls/items/{poll_id}/export',response_class=Response,responses={200:{'content':{'application/octet-stream':{'schema':{'type':'string','format':'binary'}}}}})
    async def export(request:Request,guild_id:int,poll_id:int,format:str='csv',a=Depends(actor)):
        try:
            data=service.export(a,poll_id,format)
            if len(data)>8*1024*1024:raise PollError('export_too_large')
            return Response(data,media_type='application/octet-stream',headers={'Content-Disposition':f'attachment; filename="poll-{poll_id}.{format}"','Cache-Control':'no-store'})
        except PollError as exc:raise failure(exc) from exc

    @router.get('/guilds/{guild_id}/polls/settings',response_model=schemas.PollSettingsItem)
    async def settings(request:Request,guild_id:int,a=Depends(actor)):
        try:
            service.require(a,'view')
            module=repo.settings.get_module(guild_id,'advanced_polls')
            return {'revision':module['revision'],'settings':module['settings'],'enabled':module['enabled']}
        except PollError as exc:raise failure(exc) from exc

    @router.get('/guilds/{guild_id}/polls/settings/history',response_model=schemas.Items[schemas.PollEvent])
    async def settings_history(request:Request,guild_id:int,a=Depends(actor)):
        try:
            service.require(a,'view')
            return {'items':wire(repo.settings_history(guild_id))}
        except PollError as exc:raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/polls/items/{poll_id}/delivery/{job_id}/retry',dependencies=[Depends(auth.csrf)],response_model=schemas.StatusResponse,openapi_extra=request_schema(schemas.PollRevisionInput))
    async def retry(request:Request,guild_id:int,poll_id:int,job_id:int,a=Depends(actor)):
        body=await read_body(request,schemas.PollRevisionInput)
        try:
            service.require(a,'manage')
            repo.retry_delivery(guild_id,poll_id,job_id,a.user_id,body['revision'],principal=a)
            return {'status':'queued'}
        except PollError as exc:raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/polls/items/{poll_id}/votes/remove',dependencies=[Depends(auth.csrf)],response_model=schemas.StatusResponse,openapi_extra=request_schema(schemas.PollRemoveVoteInput))
    async def remove_vote(request:Request,guild_id:int,poll_id:int,a=Depends(actor)):
        body=await read_body(request,schemas.PollRemoveVoteInput)
        try:
            service.require(a,'manage_votes')
            user=int(ids([body['user_id']])[0])
            repo.remove_vote(guild_id,poll_id,a.user_id,user,body['revision'],principal=a)
            return {'status':'removed'}
        except PollError as exc:raise failure(exc) from exc

    @router.put('/guilds/{guild_id}/polls/settings',dependencies=[Depends(auth.csrf)],response_model=schemas.PollSettingsItem,openapi_extra=request_schema(schemas.PollSettingsInput))
    async def update_settings(request:Request,guild_id:int,a=Depends(actor)):
        body=await read_body(request,schemas.PollSettingsInput)
        try:
            old=repo.settings.get_module(guild_id,'advanced_polls')
            new={**old['settings'],**body['settings']}
            for key,permission in (('retention_days','settings'),('role_weights','weights'),('role_permissions','permissions')):
                if new[key]!=old['settings'][key]:service.require(a,permission)
            resources=await GuildResources.fetch(context.discord,guild_id,live=True,assignable_roles=False)
            if any(int(role) not in resources.role_ids for role in list(new['role_weights'])+list(new['role_permissions'])):raise PollError('invalid')
            result=repo.save_settings(a,new,body['revision'],enabled=body.get('enabled'))
            return {'revision':result['revision'],'settings':result['settings'],'enabled':result['enabled']}
        except PollError as exc:raise failure(exc) from exc
        except RuntimeError as exc:raise failure(PollError('conflict')) from exc
        except ValueError as exc:raise failure(PollError('invalid')) from exc
    return router
