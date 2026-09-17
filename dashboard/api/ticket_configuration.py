"""Ticket configuration API routes."""
from __future__ import annotations
from .errors import api_error, revision_conflict
from fastapi import Depends
from typing import Any
from fastapi import APIRouter, Request
from fastapi.responses import Response
from ticketing import default_deployment, validate_form, validate_panel, validate_panel_bundle, validate_settings
from .context import ApiContext
from .route import ApiRoute, ERROR_RESPONSES
from . import schemas
from .schemas import inputs
from .body import read_body, request_schema
from .dependencies import ApiDependencies
from .ticket_dependencies import TicketDependencies
from .ticket_resources import TicketResources
from .ticket_presentation import ticket_ids
from .ticket_presentation import ticket_bundle_payload

def create_router(context: ApiContext) -> APIRouter:
    router = APIRouter(route_class=ApiRoute, responses=ERROR_RESPONSES)
    auth = ApiDependencies(context.dashboard_repository, context.discord)
    ticket_repository = context.ticket_repository
    ticket_transcripts = context.ticket_transcripts
    ticket_service = context.ticket_service
    ticket_access = TicketDependencies(context, auth)
    ticket_resources = TicketResources(context.discord)
    validate_ticket_resources = ticket_resources.validate_ticket_resources
    validate_ticket_bundle_resources = ticket_resources.validate_ticket_bundle_resources

    @router.get('/guilds/{guild_id}/tickets/settings', response_model=schemas.TicketSettings, response_model_exclude_unset=True)
    async def ticket_settings(request: Request, guild_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.manager)) -> dict[str, Any]:
        return ticket_ids(ticket_repository.settings(guild_id))

    @router.put('/guilds/{guild_id}/tickets/settings', dependencies=[Depends(auth.csrf)], response_model=schemas.TicketSettings, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.TicketSettingsInput))
    async def save_ticket_settings(request: Request, guild_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.write_manager)) -> dict[str, Any]:
        actor, _ = _ticket_actor
        try:
            body = await read_body(request, inputs.TicketSettingsInput)
            value = validate_settings(body)
            await validate_ticket_resources(guild_id, value)
            if value['enabled'] and (not ticket_transcripts.available):
                raise ValueError('TICKET_ENCRYPTION_KEY')
            if body.get('revision') is None:
                raise ValueError('revision')
            saved = ticket_repository.save_settings(guild_id, value, int(body['revision']))
            for ticket in ticket_repository.tickets(guild_id, status='open', limit=200):
                ticket_service.schedule_ticket(ticket)
            ticket_repository.audit(guild_id, 'settings_updated', actor, detail={})
            return ticket_ids(saved)
        except RuntimeError as exc:
            raise revision_conflict('別の管理者がTicket設定を更新しました。') from exc
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'ticket_settings_invalid', str(exc) or 'Ticket設定を確認してください。') from exc

    @router.get('/guilds/{guild_id}/tickets/forms', response_model=schemas.Items[schemas.TicketForm], response_model_exclude_unset=True)
    async def ticket_forms(request: Request, guild_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.manager)) -> dict[str, Any]:
        return {'items': ticket_repository.forms(guild_id)}

    @router.post('/guilds/{guild_id}/tickets/forms', status_code=201, dependencies=[Depends(auth.csrf)], response_model=schemas.TicketForm, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.TicketFormInput))
    async def create_ticket_form(request: Request, guild_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.write_manager)) -> dict[str, Any]:
        try:
            return ticket_repository.save_form(guild_id, validate_form(await read_body(request, inputs.TicketFormInput)))
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'ticket_form_invalid', str(exc)) from exc

    @router.put('/guilds/{guild_id}/tickets/forms/{form_id}', dependencies=[Depends(auth.csrf)], response_model=schemas.TicketForm, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.TicketFormInput))
    async def update_ticket_form(request: Request, guild_id: int, form_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.write_manager)) -> dict[str, Any]:
        body = await read_body(request, inputs.TicketFormInput)
        try:
            return ticket_repository.save_form(guild_id, validate_form(body), form_id, int(body['revision']) if body.get('revision') else None)
        except RuntimeError as exc:
            raise revision_conflict('Formが更新されています。') from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise api_error(422, 'ticket_form_invalid', str(exc)) from exc

    @router.get('/guilds/{guild_id}/tickets/teams', response_model=schemas.Items[schemas.TicketTeam], response_model_exclude_unset=True)
    async def ticket_teams(request: Request, guild_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.manager)) -> dict[str, Any]:
        return {'items': [ticket_ids(item) for item in ticket_repository.teams(guild_id)]}

    @router.post('/guilds/{guild_id}/tickets/teams', status_code=201, dependencies=[Depends(auth.csrf)], response_model=schemas.TicketTeam, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.TicketTeamInput))
    async def create_ticket_team(request: Request, guild_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.write_manager)) -> dict[str, Any]:
        body = await read_body(request, inputs.TicketTeamInput)
        try:
            await validate_ticket_resources(guild_id, body)
            return ticket_ids(ticket_repository.save_team(guild_id, body))
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'ticket_team_invalid', str(exc)) from exc

    @router.put('/guilds/{guild_id}/tickets/teams/{team_id}', dependencies=[Depends(auth.csrf)], response_model=schemas.TicketTeam, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.TicketTeamInput))
    async def update_ticket_team(request: Request, guild_id: int, team_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.write_manager)) -> dict[str, Any]:
        body = await read_body(request, inputs.TicketTeamInput)
        try:
            await validate_ticket_resources(guild_id, body)
            return ticket_ids(ticket_repository.save_team(guild_id, body, team_id, int(body['revision']) if body.get('revision') else None))
        except RuntimeError as exc:
            raise revision_conflict('Teamが更新されています。') from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise api_error(422, 'ticket_team_invalid', str(exc)) from exc

    @router.get('/guilds/{guild_id}/tickets/panels', response_model=schemas.Items[schemas.TicketPanel], response_model_exclude_unset=True)
    async def ticket_panels(request: Request, guild_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.manager)) -> dict[str, Any]:
        return {'items': [ticket_ids(item) for item in ticket_repository.panels(guild_id)]}

    @router.get('/guilds/{guild_id}/tickets/panels/{panel_id}/editor', response_model=schemas.TicketPanelBundle, response_model_exclude_unset=True)
    async def ticket_panel_editor(request: Request, guild_id: int, panel_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.manager)) -> dict[str, Any]:
        bundle = ticket_repository.panel_bundle(guild_id, panel_id)
        if not bundle:
            raise api_error(404, 'ticket_panel_not_found', 'Panelが見つかりません。')
        return ticket_bundle_payload(bundle)

    @router.post('/guilds/{guild_id}/tickets/panels/bundles', status_code=201, dependencies=[Depends(auth.csrf)], response_model=schemas.TicketPanelBundle, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.TicketPanelBundleInput))
    async def create_ticket_panel_bundle(request: Request, guild_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.write_manager)) -> dict[str, Any]:
        actor, _ = _ticket_actor
        try:
            body = await read_body(request, inputs.TicketPanelBundleInput)
            value = validate_panel_bundle(body)
            await validate_ticket_bundle_resources(guild_id, value)
            saved = ticket_repository.save_panel_bundle(guild_id, body)
            ticket_repository.audit(guild_id, 'panel_created', actor, detail={'panel_id': saved['panel']['id']})
            return ticket_bundle_payload(saved)
        except RuntimeError as exc:
            if str(exc) == 'panel_recovery_required':
                raise api_error(409, 'panel_recovery_required', 'Panelの投稿または削除を確認中です。復旧後に移動してください。') from exc
            raise revision_conflict('設置メッセージが更新されています。再読込してください。') from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise api_error(422, 'ticket_panel_invalid', str(exc) or 'Ticket設定を確認してください。') from exc

    @router.put('/guilds/{guild_id}/tickets/panels/{panel_id}/bundle', dependencies=[Depends(auth.csrf)], response_model=schemas.TicketPanelBundle, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.TicketPanelBundleInput))
    async def update_ticket_panel_bundle(request: Request, guild_id: int, panel_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.write_manager)) -> dict[str, Any]:
        actor, _ = _ticket_actor
        try:
            body = await read_body(request, inputs.TicketPanelBundleInput)
            value = validate_panel_bundle(body)
            await validate_ticket_bundle_resources(guild_id, value)
            saved = ticket_repository.save_panel_bundle(guild_id, body, panel_id)
            for ticket in ticket_repository.tickets(guild_id, status='open', limit=200):
                if int(ticket['panel_id']) == panel_id:
                    ticket_service.schedule_ticket(ticket)
            ticket_repository.audit(guild_id, 'panel_updated', actor, detail={'panel_id': panel_id})
            return ticket_bundle_payload(saved)
        except RuntimeError as exc:
            if str(exc) == 'panel_recovery_required':
                raise api_error(409, 'panel_recovery_required', 'Panelの投稿または削除を確認中です。復旧後に移動してください。') from exc
            raise revision_conflict('Panelまたは設置メッセージが別の管理者に更新されています。') from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise api_error(422, 'ticket_panel_invalid', str(exc) or 'Ticket設定を確認してください。') from exc

    @router.post('/guilds/{guild_id}/tickets/panels/preview', response_model=schemas.TicketPanelPreview, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.TicketPanelBundleInput))
    async def preview_ticket_panel(request: Request, guild_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.manager)) -> dict[str, Any]:
        try:
            value = validate_panel_bundle(await read_body(request, inputs.TicketPanelBundleInput))
            sample = {'ticket_number': '42', 'user': '@member', 'username': 'member', 'user_id': '123456789', 'panel': value['panel']['name'], 'team': 'Support'}

            def render(text: str) -> str:
                for key, replacement in sample.items():
                    text = text.replace('{' + key + '}', replacement)
                return text
            welcome = value['panel']['welcome_embed']
            rendered = {**welcome, 'title': render(welcome['title']), 'description': render(welcome['description']), 'author': {**welcome['author'], 'name': render(welcome['author']['name'])}, 'footer': {**welcome['footer'], 'text': render(welcome['footer']['text'])}, 'fields': [{**field, 'name': render(field['name']), 'value': render(field['value'])} for field in welcome['fields']]}
            return {'panel_message': value['deployment'], 'button': value['panel']['button'], 'welcome_message': rendered}
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'ticket_panel_preview_invalid', str(exc)) from exc

    @router.post('/guilds/{guild_id}/tickets/panels/{panel_id}/duplicate', status_code=201, dependencies=[Depends(auth.csrf)], response_model=schemas.TicketPanelBundle, response_model_exclude_unset=True)
    async def duplicate_ticket_panel(request: Request, guild_id: int, panel_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.write_manager)) -> dict[str, Any]:
        actor, _ = _ticket_actor
        bundle = ticket_repository.panel_bundle(guild_id, panel_id)
        if not bundle:
            raise api_error(404, 'ticket_panel_not_found', 'Panelが見つかりません。')
        panel = {**bundle['panel'], 'name': str(bundle['panel']['name'] + ' のコピー')[:80], 'enabled': False}
        panel.pop('id', None)
        panel.pop('revision', None)
        panel.pop('guild_id', None)
        saved = ticket_repository.save_panel_bundle(guild_id, {'panel': panel, 'deployment': default_deployment()})
        ticket_repository.audit(guild_id, 'panel_duplicated', actor, detail={'source_panel_id': panel_id, 'panel_id': saved['panel']['id']})
        return ticket_bundle_payload(saved)

    @router.post('/guilds/{guild_id}/tickets/panels/{panel_id}/detach', status_code=202, dependencies=[Depends(auth.csrf)], response_model=schemas.StatusResponse, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.DetachInput))
    async def detach_ticket_panel(request: Request, guild_id: int, panel_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.write_manager)) -> dict[str, Any]:
        actor, _ = _ticket_actor
        body = await read_body(request, inputs.DetachInput)
        if not ticket_repository.detach_panel(guild_id, panel_id, int(body.get('panel_message_id', 0))):
            raise api_error(404, 'ticket_panel_message_not_found', '設置済みPanelが見つかりません。')
        ticket_repository.audit(guild_id, 'panel_detach_queued', actor, detail={'panel_id': panel_id})
        return {'status': 'queued'}

    @router.delete('/guilds/{guild_id}/tickets/panels/{panel_id}', status_code=204, dependencies=[Depends(auth.csrf)])
    async def archive_ticket_panel(request: Request, guild_id: int, panel_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.write_manager)) -> Response:
        actor, _ = _ticket_actor
        if not ticket_repository.archive_panel(guild_id, panel_id):
            raise api_error(404, 'ticket_panel_not_found', 'Panelが見つかりません。')
        ticket_repository.audit(guild_id, 'panel_archived', actor, detail={'panel_id': panel_id})
        return Response(status_code=204)

    @router.get('/guilds/{guild_id}/tickets/panels/{panel_id}/export', response_model=schemas.TicketExport, response_model_exclude_unset=True)
    async def export_ticket_panel(request: Request, guild_id: int, panel_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.manager)) -> dict[str, Any]:
        bundle = ticket_repository.panel_bundle(guild_id, panel_id)
        if not bundle:
            raise api_error(404, 'ticket_panel_not_found', 'Panelが見つかりません。')
        panel = dict(bundle['panel'])
        [panel.pop(key, None) for key in ('id', 'guild_id', 'revision', 'created_at', 'updated_at', 'archived_at')]
        team = ticket_repository.team(guild_id, int(panel['team_id'])) if panel.get('team_id') else None
        forms = [ticket_repository.form(guild_id, int(form_id)) for form_id in {panel.get('form_id'), panel.get('exit_form_id')} if form_id]
        return {'schema': 'tueka.ticket-panel.v1', 'panel': panel, 'team': team, 'forms': [item for item in forms if item], 'deployment': default_deployment()}

    @router.post('/guilds/{guild_id}/tickets/panels/import', status_code=201, dependencies=[Depends(auth.csrf)], response_model=schemas.TicketPanelBundle, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.TicketImportInput))
    async def import_ticket_panel(request: Request, guild_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.write_manager)) -> dict[str, Any]:
        actor, _ = _ticket_actor
        body = await read_body(request, inputs.TicketImportInput)
        if body.get('schema') != 'tueka.ticket-panel.v1':
            raise api_error(422, 'ticket_import_version', '対応していないExport形式です。')
        try:
            value = {'panel': {**body.get('panel', {}), **body.get('mapping', {}), 'enabled': False}, 'deployment': default_deployment()}
            normalized = validate_panel_bundle(value)
            await validate_ticket_bundle_resources(guild_id, normalized)
            saved = ticket_repository.save_panel_bundle(guild_id, value)
            ticket_repository.audit(guild_id, 'panel_imported', actor, detail={'panel_id': saved['panel']['id']})
            return ticket_bundle_payload(saved)
        except (KeyError, TypeError, ValueError) as exc:
            raise api_error(422, 'ticket_import_mapping_required', str(exc), fields=['team_id', 'category_id', 'form_id', 'exit_form_id']) from exc

    @router.post('/guilds/{guild_id}/tickets/panels', status_code=201, dependencies=[Depends(auth.csrf)], response_model=schemas.TicketPanel, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.TicketPanelInput))
    async def create_ticket_panel(request: Request, guild_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.write_manager)) -> dict[str, Any]:
        body = await read_body(request, inputs.TicketPanelInput)
        try:
            value = validate_panel(body)
            await validate_ticket_resources(guild_id, value)
            return ticket_ids(ticket_repository.save_panel(guild_id, value))
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'ticket_panel_invalid', str(exc)) from exc

    @router.put('/guilds/{guild_id}/tickets/panels/{panel_id}', dependencies=[Depends(auth.csrf)], response_model=schemas.TicketPanel, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.TicketPanelInput))
    async def update_ticket_panel(request: Request, guild_id: int, panel_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.write_manager)) -> dict[str, Any]:
        body = await read_body(request, inputs.TicketPanelInput)
        try:
            value = validate_panel(body)
            await validate_ticket_resources(guild_id, value)
            saved = ticket_repository.save_panel(guild_id, value, panel_id, int(body['revision']) if body.get('revision') else None)
            for ticket in ticket_repository.tickets(guild_id, status='open', limit=200):
                if int(ticket['panel_id']) == panel_id:
                    ticket_service.schedule_ticket(ticket)
            return ticket_ids(saved)
        except RuntimeError as exc:
            raise revision_conflict('Panelが更新されています。') from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise api_error(422, 'ticket_panel_invalid', str(exc)) from exc

    @router.get('/guilds/{guild_id}/tickets/panel-messages', response_model=schemas.Items[schemas.TicketPanelMessage], response_model_exclude_unset=True)
    async def ticket_panel_messages(request: Request, guild_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.manager)) -> dict[str, Any]:
        return {'items': [ticket_ids(item) for item in ticket_repository.panel_messages(guild_id)]}

    @router.post('/guilds/{guild_id}/tickets/panel-messages', status_code=201, dependencies=[Depends(auth.csrf)], response_model=schemas.TicketPanelMessage, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.TicketPanelMessageInput))
    async def create_ticket_panel_message(request: Request, guild_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.write_manager)) -> dict[str, Any]:
        body = await read_body(request, inputs.TicketPanelMessageInput)
        try:
            await validate_ticket_resources(guild_id, body)
            return ticket_ids(ticket_repository.save_panel_message(guild_id, body))
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'ticket_panel_message_invalid', str(exc)) from exc

    @router.get('/guilds/{guild_id}/tickets/tags', response_model=schemas.Items[schemas.TicketTag], response_model_exclude_unset=True)
    async def ticket_tags(request: Request, guild_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.staff)) -> dict[str, Any]:
        return {'items': ticket_repository.tags(guild_id)}

    @router.post('/guilds/{guild_id}/tickets/tags', status_code=201, dependencies=[Depends(auth.csrf)], response_model=schemas.TicketTag, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.TicketTagInput))
    async def save_ticket_tag(request: Request, guild_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.write_staff)) -> dict[str, Any]:
        actor, _ = _ticket_actor
        body = await read_body(request, inputs.TicketTagInput)
        try:
            return ticket_repository.save_tag(guild_id, str(body.get('name', '')), str(body.get('content', '')), actor)
        except ValueError as exc:
            raise api_error(422, 'ticket_tag_invalid', 'Tag名は英数字・_・-、本文は2000文字以内で入力してください。') from exc

    @router.delete('/guilds/{guild_id}/tickets/tags/{tag_id}', status_code=204, dependencies=[Depends(auth.csrf)])
    async def delete_ticket_tag(request: Request, guild_id: int, tag_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.write_manager)) -> Response:
        if not ticket_repository.delete_tag(guild_id, tag_id):
            raise api_error(404, 'ticket_tag_not_found', 'Tagが見つかりません。')
        return Response(status_code=204)

    @router.get('/guilds/{guild_id}/tickets/stats', response_model=schemas.TicketStats, response_model_exclude_unset=True)
    async def ticket_stats(request: Request, guild_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.manager)) -> dict[str, Any]:
        return ticket_repository.statistics(guild_id)
    return router
