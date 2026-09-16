"""Tickets API routes."""
from __future__ import annotations
from .errors import api_error
from fastapi import Depends
import sqlite3
import time
from typing import Any
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from ticketing import TicketValidationError
from .context import ApiContext
from .dependencies import ApiDependencies
from .ticket_dependencies import TicketDependencies
from .ticket_presentation import ticket_ids

def create_router(context: ApiContext) -> APIRouter:
    router = APIRouter()
    auth = ApiDependencies(context.dashboard_repository, context.discord)
    discord = context.discord
    settings = context.settings
    ticket_repository = context.ticket_repository
    ticket_transcripts = context.ticket_transcripts
    ticket_service = context.ticket_service
    token = auth.token
    ticket_access = TicketDependencies(context, auth)
    ticket_actor = ticket_access.ticket_actor
    ticket_subject_access = ticket_access.ticket_subject_access

    @router.get('/guilds/{guild_id}/tickets')
    async def ticket_overview(request: Request, guild_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.staff)) -> dict[str, Any]:
        actor, administrator = _ticket_actor
        recent = []
        for item in ticket_repository.tickets(guild_id, limit=10):
            try:
                await ticket_subject_access(request, guild_id, item, actor, administrator)
                recent.append(ticket_ids(item))
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
        return {'settings': ticket_ids(ticket_repository.settings(guild_id)), 'summary': ticket_repository.summary(guild_id), 'recent': recent, 'transcript_storage': {'available': ticket_transcripts.available, 's3_configured': bool(settings.ticket_s3_bucket)}, 'can_manage': administrator}

    @router.get('/guilds/{guild_id}/tickets/items')
    async def ticket_items(request: Request, guild_id: int, status: str | None=None, before: int | None=None, _ticket_actor: tuple[int, bool]=Depends(ticket_access.staff)) -> dict[str, Any]:
        actor, administrator = _ticket_actor
        visible = []
        for item in ticket_repository.tickets(guild_id, status=status, before=before):
            try:
                await ticket_subject_access(request, guild_id, item, actor, administrator)
                visible.append(ticket_ids(item))
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
        return {'items': visible, 'next': int(visible[-1]['id']) if visible else None}

    @router.get('/guilds/{guild_id}/tickets/items/{ticket_id}')
    async def ticket_detail(request: Request, guild_id: int, ticket_id: int, after: int=0, _ticket_actor: tuple[int, bool]=Depends(ticket_access.staff)) -> dict[str, Any]:
        actor, administrator = _ticket_actor
        ticket = ticket_repository.ticket(ticket_id)
        if not ticket or int(ticket['guild_id']) != guild_id:
            raise api_error(404, 'ticket_not_found', 'Ticketが見つかりません。')
        await ticket_subject_access(request, guild_id, ticket, actor, administrator)
        messages = ticket_repository.messages(ticket_id, after=after)
        safe_ticket = ticket_ids(ticket)
        safe_ticket['form_answers'] = {key: ticket_transcripts.decrypt_text(value) for key, value in dict(ticket.get('form_answers') or {}).items()}
        return {'ticket': safe_ticket, 'panel': ticket_ids(ticket_repository.panel(guild_id, int(ticket['panel_id'])) or {}), 'messages': [{**ticket_ids(item), 'content': ticket_transcripts.decrypt_text(item.get('encrypted_content'))} for item in messages], 'transcript': ticket_ids(ticket_repository.transcript_for_ticket(ticket_id) or {}), 'outbox': ticket_repository.outbox(ticket_id)}

    @router.post('/guilds/{guild_id}/tickets/items/{ticket_id}/reply', status_code=202, dependencies=[Depends(auth.csrf)])
    async def ticket_reply(request: Request, guild_id: int, ticket_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.write_staff)) -> dict[str, Any]:
        actor, administrator = _ticket_actor
        body = await request.json()
        ticket = ticket_repository.ticket(ticket_id)
        if not ticket or int(ticket['guild_id']) != guild_id:
            raise api_error(404, 'ticket_not_found', 'Ticketが見つかりません。')
        await ticket_subject_access(request, guild_id, ticket, actor, administrator)
        user = await discord.current_user(token(request))
        panel = ticket_repository.panel(guild_id, int(ticket['panel_id'])) or {}
        try:
            item = ticket_service.queue_reply(ticket_id, actor, user.get('global_name') or user['username'], str(body.get('content', '')), anonymous=bool(body.get('anonymous') or panel.get('anonymous_dashboard_replies')), note=bool(body.get('note')))
            return {'id': item['id'], 'status': item['status']}
        except TicketValidationError as exc:
            raise api_error(422, exc.code, str(exc)) from exc

    @router.post('/guilds/{guild_id}/tickets/items/{ticket_id}/action', status_code=202, dependencies=[Depends(auth.csrf)])
    async def ticket_action(request: Request, guild_id: int, ticket_id: int, _ticket_actor: tuple[int, bool]=Depends(ticket_access.write_staff)) -> dict[str, Any]:
        actor, administrator = _ticket_actor
        body = await request.json()
        ticket = ticket_repository.ticket(ticket_id)
        if not ticket or int(ticket['guild_id']) != guild_id:
            raise api_error(404, 'ticket_not_found', 'Ticketが見つかりません。')
        await ticket_subject_access(request, guild_id, ticket, actor, administrator)
        action = str(body.get('action', ''))
        if action not in {'claim', 'unclaim', 'close', 'reopen', 'delete', 'exclude_auto_close', 'awaiting_user'}:
            raise api_error(422, 'ticket_action_invalid', '操作を確認してください。')
        item = ticket_repository.queue_outbox(ticket_id, action, actor, {'reason': str(body.get('reason', ''))[:1000], 'revision': body.get('revision'), 'excluded': body.get('excluded', True)})
        return {'id': item['id'], 'status': item['status']}

    @router.get('/tickets/transcripts/{transcript_id}')
    async def ticket_transcript(request: Request, transcript_id: int) -> dict[str, Any]:
        if not ticket_repository or not ticket_transcripts:
            raise HTTPException(404)
        transcript = ticket_repository.transcript(transcript_id)
        if not transcript or transcript.get('status') != 'ready' or int(transcript['expires_at']) < int(time.time()):
            raise api_error(404, 'transcript_not_found', 'Transcriptが見つかりません。')
        access = token(request)
        user = await discord.current_user(access)
        user_id = int(user['id'])
        if user_id != int(transcript['opener_id']):
            actor, administrator = await ticket_actor(request, int(transcript['guild_id']))
            ticket = ticket_repository.ticket(int(transcript['ticket_id']))
            if ticket:
                await ticket_subject_access(request, int(transcript['guild_id']), ticket, actor, administrator)
        ticket_repository.audit(int(transcript['guild_id']), 'transcript_viewed', user_id, int(transcript['ticket_id']), {'transcript_id': transcript_id})
        payload = await ticket_transcripts.load(transcript['backend'], transcript['object_key'], transcript['content_hash'])
        panel = ticket_repository.panel(int(transcript['guild_id']), int(transcript['panel_id']))
        payload['feedback_enabled'] = bool(panel and panel.get('feedback_enabled'))
        payload['feedback_form'] = ticket_repository.form(int(transcript['guild_id']), int(panel['exit_form_id'])) if panel and panel.get('exit_form_id') else None
        return payload

    @router.get('/tickets/attachments/{attachment_id}')
    async def ticket_attachment(request: Request, attachment_id: int) -> Response:
        if not ticket_repository or not ticket_transcripts:
            raise HTTPException(404)
        attachment = ticket_repository.attachment(attachment_id)
        if not attachment or attachment.get('status') != 'ready':
            raise api_error(404, 'attachment_not_found', '添付ファイルが見つかりません。')
        access = token(request)
        user = await discord.current_user(access)
        user_id = int(user['id'])
        if user_id != int(attachment['opener_id']):
            actor, administrator = await ticket_actor(request, int(attachment['guild_id']))
            ticket = ticket_repository.ticket(int(attachment['ticket_id']))
            if ticket:
                await ticket_subject_access(request, int(attachment['guild_id']), ticket, actor, administrator)
        content = await ticket_transcripts.load_attachment(str(attachment['backend']), str(attachment['object_key']), str(attachment['content_hash']))
        ticket_repository.audit(int(attachment['guild_id']), 'attachment_downloaded', user_id, int(attachment['ticket_id']), {'attachment_id': attachment_id})
        filename = quote(str(attachment['filename']), safe='')
        return Response(content, media_type='application/octet-stream', headers={'Content-Disposition': f"attachment; filename*=UTF-8''{filename}", 'X-Content-Type-Options': 'nosniff'})

    @router.post('/tickets/{ticket_id}/feedback', status_code=201, dependencies=[Depends(auth.csrf)])
    async def ticket_feedback(request: Request, ticket_id: int) -> dict[str, Any]:
        if not ticket_repository or not ticket_transcripts:
            raise HTTPException(404)
        ticket = ticket_repository.ticket(ticket_id)
        if not ticket:
            raise api_error(404, 'ticket_not_found', 'Ticketが見つかりません。')
        panel = ticket_repository.panel(int(ticket['guild_id']), int(ticket['panel_id']))
        if not panel or not panel.get('feedback_enabled'):
            raise api_error(403, 'feedback_disabled', 'このTicketでは評価を受け付けていません。')
        user = await discord.current_user(token(request))
        user_id = int(user['id'])
        body = await request.json()
        comment = str(body.get('comment') or '').strip()
        if len(comment) > 1000:
            raise api_error(422, 'feedback_invalid', 'コメントは1000文字以内で入力してください。')
        try:
            form = ticket_repository.form(int(ticket['guild_id']), int(panel['exit_form_id'])) if panel.get('exit_form_id') else None
            answers = {str(key): str(value).strip() for key, value in dict(body.get('answers') or {}).items()}
            if form:
                permitted = {field['key'] for field in form['fields']}
                if set(answers) - permitted:
                    raise ValueError('feedback_answers')
                for field in form['fields']:
                    answer = answers.get(field['key'], '')
                    if field['required'] and (not answer):
                        raise ValueError(field['key'])
                    if answer and (not int(field['min_length']) <= len(answer) <= int(field['max_length'])):
                        raise ValueError(field['key'])
            elif answers:
                raise ValueError('feedback_answers')
            encrypted_answers = {key: ticket_transcripts.encrypt_text(value) for key, value in answers.items()}
            saved = ticket_repository.save_feedback(ticket_id, user_id, int(body.get('rating', 0)), ticket_transcripts.encrypt_text(comment) if comment else None, int(form['id']) if form else None, encrypted_answers)
            ticket_repository.audit(int(ticket['guild_id']), 'feedback_submitted', user_id, ticket_id, {'rating': saved['rating']})
            return {'rating': saved['rating'], 'created_at': saved['created_at']}
        except PermissionError as exc:
            raise api_error(403, 'feedback_forbidden', 'このTicketを評価できません。') from exc
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'feedback_invalid', '評価は1～5で指定してください。') from exc
        except sqlite3.IntegrityError as exc:
            raise api_error(409, 'feedback_exists', 'このTicketは評価済みです。') from exc
    return router
