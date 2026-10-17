"""Manager-only private appeal review, replies, Ticket links and DM retry."""
from fastapi import APIRouter, Depends, Request
from dashboard.api.dependencies import ApiDependencies
from dashboard.api.route import ApiRoute, ERROR_RESPONSES
from dashboard.api.body import read_body, request_schema
from dashboard.api.errors import api_error, revision_conflict
from dashboard.api import schemas
from appeals.service import AppealService


def wire(value):
    if isinstance(value,list):return [wire(v) for v in value]
    if isinstance(value,dict):
        return {k:str(v) if k in ('guild_id','author_id','actor_id','original_moderator_id','discord_message_id') and v is not None else wire(v)
                for k,v in value.items() if k != 'interaction_id'}
    return value


def create_router(context):
    router=APIRouter(route_class=ApiRoute,responses=ERROR_RESPONSES)
    auth=ApiDependencies(context.dashboard_repository,context.discord)
    repo=context.appeal_repository
    service=AppealService(repo,context.moderation_repository,context.application_repository,context.ticket_repository)

    async def actor(request):
        return int((await context.discord.current_user(auth.token(request)))['id'])

    def failure(exc):
        if isinstance(exc,LookupError):return api_error(404,'appeal_not_found','保存期限内のやり取りが見つかりません。')
        if isinstance(exc,PermissionError):return api_error(403,'appeal_forbidden','受付が無効、対象が別の利用者、または独立した審査者ではありません。')
        if isinstance(exc,RuntimeError):return revision_conflict('状態が更新されています。再読み込みしてください。')
        return api_error(422,'appeal_invalid','入力内容と対象を確認してください。')

    @router.get('/guilds/{guild_id}/appeals/items',response_model=schemas.Items[schemas.AppealItem])
    async def items(request:Request,guild_id:int,before:int|None=None,limit:int=50,_access=Depends(auth.read)):
        return {'items':wire(repo.items(guild_id,before=before,limit=limit))}

    @router.get('/guilds/{guild_id}/appeals/items/{item_id}',response_model=schemas.AppealConversation)
    async def detail(request:Request,guild_id:int,item_id:int,_access=Depends(auth.read)):
        try:return wire(repo.conversation(guild_id,item_id))
        except LookupError as exc:raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/appeals/items/{item_id}/reply',dependencies=[Depends(auth.csrf)],response_model=schemas.AppealItem,openapi_extra=request_schema(schemas.AppealReplyInput))
    async def reply(request:Request,guild_id:int,item_id:int,_access=Depends(auth.write)):
        body=await read_body(request,schemas.AppealReplyInput)
        try:return wire(repo.reply(guild_id,item_id,await actor(request),body['content'],revision=body['revision'],staff=True))
        except (ValueError,PermissionError,LookupError,RuntimeError) as exc:raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/appeals/items/{item_id}/review',dependencies=[Depends(auth.csrf)],response_model=schemas.AppealItem,openapi_extra=request_schema(schemas.AppealReviewInput))
    async def review(request:Request,guild_id:int,item_id:int,_access=Depends(auth.write)):
        body=await read_body(request,schemas.AppealReviewInput)
        try:return wire(repo.transition(guild_id,item_id,await actor(request),body['status'],body['reason'],revision=body['revision']))
        except (ValueError,PermissionError,LookupError,RuntimeError) as exc:raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/appeals/items/{item_id}/ticket',dependencies=[Depends(auth.csrf)],response_model=schemas.AppealItem,openapi_extra=request_schema(schemas.AppealTicketInput))
    async def ticket(request:Request,guild_id:int,item_id:int,_access=Depends(auth.write)):
        body=await read_body(request,schemas.AppealTicketInput)
        try:return wire(service.link_ticket(guild_id,item_id,await actor(request),body['ticket_id'],body['revision']))
        except (ValueError,PermissionError,LookupError,RuntimeError) as exc:raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/appeals/items/{item_id}/delivery/{job_id}/retry',dependencies=[Depends(auth.csrf)],response_model=schemas.AppealItem,openapi_extra=request_schema(schemas.AppealRetryInput))
    async def retry(request:Request,guild_id:int,item_id:int,job_id:int,_access=Depends(auth.write)):
        body=await read_body(request,schemas.AppealRetryInput)
        try:
            repo.retry_delivery(guild_id,item_id,job_id,await actor(request),revision=body['revision'])
            return wire(repo.item(guild_id,item_id))
        except (ValueError,PermissionError,LookupError,RuntimeError) as exc:raise failure(exc) from exc
    return router
