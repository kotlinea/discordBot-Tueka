"""Guild-manager-only form configuration and private application review."""
from fastapi import APIRouter, Depends, Request
from dashboard.api.dependencies import ApiDependencies
from dashboard.api.route import ApiRoute, ERROR_RESPONSES
from dashboard.api.body import read_body, request_schema
from dashboard.api.errors import api_error, revision_conflict
from dashboard.api import schemas
from dashboard.api.schemas.applications import ApplicationFormInput, ApplicationReviewInput


def wire_form(form):
    return {**form, 'guild_id':str(form['guild_id']), **{k:[str(v) for v in form[k]] for k in ('required_role_ids','denied_role_ids')}}


def wire_item(item):
    # The interaction id is an internal replay key, not an exposed applicant field.
    return {k:v for k,v in {**item,'guild_id':str(item['guild_id']), 'author_id':str(item['author_id']), 'snapshot':wire_form(item['snapshot'])}.items() if k != 'interaction_id'}


def create_router(context):
    router = APIRouter(route_class=ApiRoute,responses=ERROR_RESPONSES)
    auth = ApiDependencies(context.dashboard_repository,context.discord)
    repo = context.application_repository

    async def actor(request):
        return int((await context.discord.current_user(auth.token(request)))['id'])

    def failure(exc):
        if isinstance(exc, LookupError):
            return api_error(404,'application_not_found','申請またはフォームが見つかりません。')
        if isinstance(exc, PermissionError):
            return api_error(403,'application_forbidden','受付が無効、または操作権限がありません。本人の申請は審査できません。')
        if isinstance(exc, RuntimeError):
            return revision_conflict('内容または状態が更新されています。再読み込みしてください。')
        return api_error(422,'application_invalid','フォームと入力条件を確認してください。')

    @router.get('/guilds/{guild_id}/applications/forms',response_model=schemas.Items[schemas.ApplicationForm])
    async def forms(request:Request,guild_id:int,_access=Depends(auth.read)):
        return {'items':[wire_form(f) for f in repo.forms(guild_id)]}

    async def save(request,guild_id,form_id=None):
        body = await read_body(request,ApplicationFormInput)
        if form_id is not None and body.get('revision') is None:
            raise api_error(422,'revision_required','再読み込みして保存してください。')
        # Resource ids must belong to this Guild, even for disabled drafts.
        _, roles, _ = await auth.resources(request,guild_id,live=True)
        role_ids={int(r['id']) for r in roles}
        try:
            from applications.models import validate_form
            normalized=validate_form(body)
            if (set(normalized['required_role_ids']) | set(normalized['denied_role_ids'])) - role_ids:
                raise ValueError('foreign_role')
            return wire_form(repo.save_form(guild_id,await actor(request),normalized,form_id=form_id,revision=body.get('revision')))
        except (ValueError,TypeError,LookupError,RuntimeError) as exc:
            raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/applications/forms',dependencies=[Depends(auth.csrf)],response_model=schemas.ApplicationForm,openapi_extra=request_schema(ApplicationFormInput))
    async def create(request:Request,guild_id:int,_access=Depends(auth.write)):
        return await save(request,guild_id)

    @router.put('/guilds/{guild_id}/applications/forms/{form_id}',dependencies=[Depends(auth.csrf)],response_model=schemas.ApplicationForm,openapi_extra=request_schema(ApplicationFormInput))
    async def update(request:Request,guild_id:int,form_id:int,_access=Depends(auth.write)):
        return await save(request,guild_id,form_id)

    @router.get('/guilds/{guild_id}/applications/items',response_model=schemas.Items[schemas.ApplicationItem])
    async def items(request:Request,guild_id:int,before:int|None=None,limit:int=50,_access=Depends(auth.read)):
        return {'items':[wire_item(v) for v in repo.items(guild_id,before=before,limit=limit)]}

    @router.get('/guilds/{guild_id}/applications/items/{item_id}/events',response_model=schemas.Items[schemas.ApplicationEvent])
    async def events(request:Request,guild_id:int,item_id:int,_access=Depends(auth.read)):
        try:
            return {'items':[{**v,'actor_id':str(v['actor_id'])} for v in repo.events(guild_id,item_id)]}
        except LookupError as exc:
            raise failure(exc) from exc

    @router.post('/guilds/{guild_id}/applications/items/{item_id}/review',dependencies=[Depends(auth.csrf)],response_model=schemas.ApplicationItem,openapi_extra=request_schema(ApplicationReviewInput))
    async def review(request:Request,guild_id:int,item_id:int,_access=Depends(auth.write)):
        body=await read_body(request,ApplicationReviewInput)
        try:
            return wire_item(repo.transition(guild_id,item_id,await actor(request),body['status'],body['reason'],revision=body['revision']))
        except (ValueError,LookupError,RuntimeError,PermissionError) as exc:
            raise failure(exc) from exc
    return router
