"""Shared Ticket workflow service used by Discord and the dashboard."""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any

from .models import support_is_open
from .messages import welcome, close_notice
from .repository import TicketRepository
from .transcripts import TranscriptStorage
from .contracts import ContainerRef, TicketResourcePort
from discord_io import DiscordFailure
from jobs import LostLease
from jobs.leases import ResourceLease


class TicketValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class TicketService:
    def __init__(self, repository: TicketRepository, transcripts: TranscriptStorage) -> None:
        self.repository = repository
        self.transcripts = transcripts

    async def deliver_notice(self, port: TicketResourcePort, ticket: dict, item: dict, base_url: str):
        action, key = item['action'], f"{item['id']}:{item['created_at']}"
        if action == 'remove_open_mentions':
            await port.remove_open_mentions(ticket, int(item['payload']['message_id']))
            return
        panel = self.repository.panel(ticket['guild_id'], ticket['panel_id']) or {}
        settings = self.repository.settings(ticket['guild_id'])
        delivered = self.repository.notice_delivery(ticket['id'], key)
        if delivered is None:
            if action == 'welcome':
                if ticket['status'] not in {'open', 'awaiting_user'}:
                    raise ValueError('ticket_not_open')
                member = await port.member_identity(ticket)
                team = self.repository.team(ticket['guild_id'], panel['team_id']) if panel.get('team_id') else None
                answers = {key: self.transcripts.decrypt_text(value) for key, value in ticket.get('form_answers', {}).items()}
                packet = welcome(ticket, panel, member, team, answers)
            elif action == 'notify_open':
                if panel.get('mode') != 'private_thread' or not panel.get('staff_notification_channel_id'):
                    return
                packet = {'channel_id': panel['staff_notification_channel_id'], 'content': f"新しいTicket #{ticket['ticket_number']} · {panel['name']}",
                    'buttons': [{'label': 'Ticketに参加', 'style': 2, 'custom_id': f"tueka-ticket:join:{ticket['id']}"}]}
            else:
                if action == 'close_dm' and not settings.get('close_dm'):
                    return
                channel_id = panel.get('transcript_channel_id') or settings.get('transcript_channel_id')
                if action == 'close_log' and not channel_id:
                    return
                transcript = self.repository.transcript(int(item['payload']['transcript_id']))
                if transcript is None:
                    raise ValueError('Transcript unavailable')
                packet = close_notice({**ticket, 'close_reason': item['payload'].get('reason')}, panel, transcript, base_url, direct=action == 'close_dm')
                if action == 'close_log':
                    packet['channel_id'] = channel_id
            recover = self.repository.begin_delivery(ticket, key, 'notice')
            try:
                delivered = await port.notice(ticket, key, packet, recover=recover)
            except DiscordFailure as exc:
                if not recover and not exc.partial:
                    self.repository.delivery_not_sent(ticket['id'], key, 'notice')
                raise
            self.repository.finish_notice(ticket, key, delivered)
        if action == 'welcome':
            if panel.get('remove_mentions'):
                self.repository.queue_outbox(ticket['id'], 'remove_open_mentions', ticket['opener_id'], {'message_id': delivered['id'], 'parent_key': key})
            if panel.get('mode') == 'private_thread':
                self.repository.queue_outbox(ticket['id'], 'notify_open', ticket['opener_id'], {'parent_key': key})
            self.record_message(ticket, delivered['id'], None, 'Tueka', 'Ticket opened', [], kind='system', created_at=delivered['created_at'], delivery_key=key)

    async def delete_ticket(self, port: TicketResourcePort, ticket: dict):
        await port.delete_resource(ticket)
        self.repository.mark_deleted(ticket['id'], int(time.time()))

    async def change_category(self, port: TicketResourcePort, ticket: dict, item: dict):
        resume = item['action'] == 'resume_awaiting'
        if resume and ticket['status'] == 'open':
            return
        if ticket['status'] not in {'open', 'awaiting_user'}:
            raise ValueError('ticket_not_open')
        panel = self.repository.panel(ticket['guild_id'], ticket['panel_id']) or {}
        target = ticket.get('awaiting_return_category_id') if resume else panel.get('awaiting_category_id')
        if not resume and not target:
            raise ValueError('awaiting_category_unavailable')
        before = await port.category(ticket)
        intent = self.repository.category_intent(ticket, f"{item['id']}:{item['created_at']}", before, target)
        await port.move_category(ticket, intent['target'], expected=intent['before'])
        if resume:
            saved = self.repository.resume_awaiting_user(ticket['id'])
        elif ticket['status'] == 'open':
            saved = self.repository.set_awaiting_user(ticket['id'], intent['before'])
        elif ticket.get('awaiting_return_category_id') == intent['before']:
            saved = ticket
        else:
            raise RuntimeError('revision_conflict')
        self.schedule_ticket(saved)

    async def deliver_message(self, port: TicketResourcePort, ticket: dict, item: dict):
        delivery_key = f"{item['id']}:{item['created_at']}"
        payload = item['payload']
        plain = self.transcripts.decrypt_text(payload.get('content_encrypted'))
        note = item['action'] == 'note'
        if self.repository.delivery_recorded(ticket['id'], delivery_key):
            if not note:
                self.schedule_ticket(ticket)
            return
        if note and ticket['mode'] == 'private_thread':
            self.record_message(ticket, None, int(item['actor_id']), payload['actor_name'], plain, [], kind='note', delivery_key=delivery_key)
            return
        target = ticket
        if note:
            recover_notes = self.repository.begin_delivery(ticket, delivery_key, 'notes_thread')
            try:
                thread_id = await port.notes_thread(ticket, recover=recover_notes)
            except DiscordFailure as exc:
                if not recover_notes and not exc.partial:
                    self.repository.delivery_not_sent(ticket['id'], delivery_key, 'notes_thread')
                raise
            self.repository.set_notes_thread(ticket['id'], thread_id)
            target = {**ticket, 'discord_container_id': thread_id}
            await port.participant(target, int(item['actor_id']), add=True)
        recover = self.repository.begin_delivery(ticket, delivery_key, 'message')
        author = 'Support Staff' if payload.get('anonymous') else payload['actor_name']
        try:
            message = await port.send_reply(target, delivery_key, f'**{author}**\n{plain}', recover=recover)
        except DiscordFailure as exc:
            if not recover and not exc.partial:
                self.repository.delivery_not_sent(ticket['id'], delivery_key, 'message')
            raise
        self.record_message(ticket, message['id'], int(item['actor_id']), payload['actor_name'], plain, [],
                            kind='note' if note else 'staff_reply', created_at=message['created_at'], delivery_key=delivery_key)

    async def change_participant(self, port: TicketResourcePort, ticket: dict, user_id: int, actor_id: int, *, add: bool, access: str = 'member'):
        if ticket['status'] not in {'open', 'awaiting_user'}:
            raise ValueError('ticket_not_open')
        if not add and user_id == ticket['opener_id']:
            raise ValueError('opener_removal_forbidden')
        await port.participant(ticket, user_id, add=add)
        if add:
            self.repository.add_participant(ticket['id'], 'user', user_id, actor_id, access)
        else:
            self.repository.remove_participant(ticket['id'], 'user', user_id)

    async def change_claim(self, port: TicketResourcePort, ticket: dict, panel: dict, member_id: int | None, expected_revision: int | None):
        lease = ResourceLease(self.repository.database_url, 'ticket_claim', ticket['id'])
        try:
            return await lease.run(lambda owned: self._change_claim_owned(port, ticket, panel, member_id, expected_revision, owned))
        except LostLease as exc:
            raise DiscordFailure(str(exc), retry=True, partial=True) from exc

    async def _change_claim_owned(self, port, ticket, panel, member_id, expected_revision, lease):
        if expected_revision is not None and ticket['revision'] != expected_revision:
            raise RuntimeError('revision_conflict')
        team = self.repository.team(ticket['guild_id'], int(panel['team_id'])) if panel.get('team_id') else None
        changes = await port.claim_changes(ticket, panel, member_id, (team or {}).get('role_ids', []))
        operation_id = self.repository.begin_claim_change(ticket, member_id, changes, lease=lease)
        try:
            for change in changes:
                lease.renew()
                await port.permission(ticket, change)
            saved = self.repository.set_claim(ticket['id'], member_id, ticket['revision'], operation_id=operation_id, lease=lease)
        except LostLease:
            raise
        except Exception:
            if self.repository.claim_change_finished(operation_id):
                raise
            restored = True
            for change in reversed(changes):
                try:
                    lease.renew()
                    await port.permission(ticket, change, restore=True)
                except LostLease:
                    raise
                except Exception:
                    restored = False
            if restored:
                self.repository.finish_claim_change(ticket, operation_id, 'rolled_back', lease=lease)
            else:
                self.repository.audit(ticket['guild_id'], 'claim_compensation_failed', member_id, ticket['id'], {'operation_id': operation_id})
            raise
        return saved

    async def recover_claim(self, port: TicketResourcePort, operation: dict):
        lease = ResourceLease(self.repository.database_url, 'ticket_claim', operation['ticket_id'])
        try:
            return await lease.run(lambda owned: self._recover_claim_owned(port, operation, owned))
        except LostLease as exc:
            raise DiscordFailure(str(exc), retry=True, partial=True) from exc

    async def _recover_claim_owned(self, port, operation, lease):
        ticket = self.repository.ticket(operation['ticket_id'])
        if ticket is None:
            raise ValueError('Ticket unavailable')
        detail = operation['detail']
        # Claim state and its completion receipt commit atomically. A matching
        # revision/member is not evidence that this particular operation committed.
        if self.repository.claim_change_finished(operation['id']):
            return
        for change in reversed(detail['changes']):
            lease.renew()
            await port.permission(ticket, change, restore=True)
        self.repository.finish_claim_change(ticket, operation['id'], 'rolled_back', lease=lease)

    async def open_container(self, port: TicketResourcePort, ticket: dict, panel: dict, name: str) -> tuple[dict, ContainerRef]:
        current = self.repository.ticket(ticket['id']) or ticket
        if current.get('discord_container_id') and current['status'] in {'open', 'awaiting_user'}:
            return current, ContainerRef(current['discord_container_id'], current.get('parent_channel_id'))
        if current['status'] != 'creating':
            raise DiscordFailure('Ticket creation requires recovery', partial=True)
        recover = self.repository.begin_delivery(ticket, str(ticket['interaction_id']), 'container')
        if recover:
            raise DiscordFailure('Ticket creation already started; reconcile its resource', partial=True)
        team = self.repository.team(ticket['guild_id'], int(panel['team_id'])) if panel.get('team_id') else None
        resource = None
        try:
            resource = await port.create_container(ticket, panel, name, (team or {}).get('role_ids', []),
                self.repository.on_call_members(ticket['guild_id'], int(panel.get('team_id') or 0)),
                (team or {}).get('user_ids', []) + (team or {}).get('admin_user_ids', []))
            saved = self.repository.activate_ticket(ticket['id'], resource.id, resource.parent_id)
            self.schedule_ticket(saved)
            return saved, resource
        except Exception as exc:
            resource_id = resource.id if resource else getattr(exc, 'resource_id', None)
            if resource_id is not None:
                self.repository.record_orphan(ticket['guild_id'], ticket['id'], resource_id, panel['mode'], type(exc).__name__)
            self.repository.fail_ticket(ticket['id'], type(exc).__name__)
            raise

    async def recover_creation(self, port: TicketResourcePort, ticket: dict):
        panel = self.repository.panel(ticket['guild_id'], ticket['panel_id'])
        if panel is None:
            raise ValueError('Ticket panel unavailable')
        resource = await port.find_container(ticket, panel)
        self.repository.record_orphan(ticket['guild_id'], ticket['id'], resource.id, panel['mode'], 'creation_receipt_recovered')
        orphan = next(item for item in self.repository.pending_orphans(ticket['guild_id']) if item['container_id'] == resource.id)
        saved = self.repository.adopt_orphan(ticket['guild_id'], orphan['id'], resource.parent_id)
        self.schedule_ticket(saved)
        return saved

    async def recover_orphan(self, port: TicketResourcePort, guild_id: int, orphan_id: int) -> dict:
        orphan = next((row for row in self.repository.pending_orphans(guild_id) if row['id'] == orphan_id), None)
        if orphan is None:
            raise ValueError('Orphan not pending')
        ticket = self.repository.ticket(orphan['ticket_id'])
        panel = self.repository.panel(guild_id, ticket['panel_id']) if ticket else None
        if ticket is None or panel is None or ticket['guild_id'] != guild_id:
            raise ValueError('Orphan ticket/panel unavailable')
        resource = await port.recover_container(ticket, panel, orphan['container_id'])
        if resource.id != orphan['container_id']:
            raise ValueError('Orphan resource mismatch')
        saved = self.repository.adopt_orphan(guild_id, orphan_id, resource.parent_id)
        self.schedule_ticket(saved)
        return saved

    def validate_open(self, guild_id: int, panel_id: int, opener_id: int, role_ids: set[int], answers: dict[str, str] | None = None) -> tuple[dict[str, Any], dict[str, str]]:
        settings, panel = self.repository.settings(guild_id), self.repository.panel(guild_id, panel_id)
        if not settings["enabled"] or panel is None or not panel.get("enabled"):
            raise TicketValidationError("disabled", "チケット受付は現在利用できません。")
        required = set(int(item) for item in panel.get("required_role_ids", []))
        if required and not required.intersection(role_ids):
            raise TicketValidationError("panel_forbidden", "このチケットを作成する権限がありません。")
        if self.repository.is_blacklisted(guild_id, opener_id):
            raise TicketValidationError("blacklisted", "チケットの作成が制限されています。")
        access_rules = panel.get("access_rules") or []
        denied = {int(rule["role_id"]) for rule in access_rules if not rule.get("allow", True)}
        allowed = {int(rule["role_id"]) for rule in access_rules if rule.get("allow", True)}
        if denied.intersection(role_ids) or (allowed and not allowed.intersection(role_ids)):
            raise TicketValidationError("panel_forbidden", "このチケットを作成する権限がありません。")
        is_open, next_open = support_is_open(panel)
        if not is_open:
            suffix = f" 次回受付: {next_open.strftime('%Y-%m-%d %H:%M %Z')}" if next_open else ""
            raise TicketValidationError("outside_support_hours", "現在は受付時間外です。" + suffix)
        form_answers = {str(key): str(value).strip() for key, value in (answers or {}).items()}
        form = self.repository.form(guild_id, int(panel["form_id"])) if panel.get("form_id") else None
        if form:
            permitted = {field["key"] for field in form["fields"]}
            if set(form_answers) - permitted:
                raise TicketValidationError("form_invalid", "フォームに不明な回答が含まれています。")
            for field in form["fields"]:
                value = form_answers.get(field["key"], "")
                if field["required"] and not value:
                    raise TicketValidationError("form_required", f"{field['label']}を入力してください。")
                if value and not int(field["min_length"]) <= len(value) <= int(field["max_length"]):
                    raise TicketValidationError("form_length", f"{field['label']}の文字数を確認してください。")
        return panel, form_answers

    def reserve(self, guild_id: int, panel_id: int, opener_id: int, interaction_id: str, role_ids: set[int], answers: dict[str, str] | None = None, *, staff_exempt: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
        panel, normalized = self.validate_open(guild_id, panel_id, opener_id, role_ids, answers)
        encrypted_answers = {key: self.transcripts.encrypt_text(value) for key, value in normalized.items()}
        try:
            ticket = self.repository.reserve_ticket(guild_id, panel_id, opener_id, interaction_id, encrypted_answers, staff_exempt=staff_exempt)
        except ValueError as exc:
            if str(exc) == 'disabled':
                raise TicketValidationError('disabled', 'チケット受付は現在利用できません。') from exc
            raise
        except OverflowError as exc:
            code = str(exc)
            if code.startswith("ticket_cooldown:"):
                seconds = code.partition(":")[2]
                raise TicketValidationError("ticket_cooldown", f"次のチケットを作成できるまであと{seconds}秒です。") from exc
            if code == "user_ticket_limit":
                raise TicketValidationError("user_ticket_limit", "この種類で同時に開けるチケット数の上限に達しています。") from exc
            raise TicketValidationError("ticket_limit", "サーバー全体の同時受付上限に達しています。") from exc
        self.repository.audit(guild_id, "ticket_reserved", opener_id, ticket["id"], {"panel_id": panel_id})
        return ticket, panel

    @staticmethod
    def channel_name(ticket: dict[str, Any], panel: dict[str, Any], username: str) -> str:
        values = {"number": ticket["ticket_number"], "username": username, "user_id": ticket["opener_id"], "panel": panel["name"]}
        result = str(panel.get("ticket_name_template") or "ticket-{number}-{username}")
        for key, value in values.items():
            result = result.replace("{" + key + "}", str(value))
        result = re.sub(r"[^a-zA-Z0-9ぁ-んァ-ヶ一-龠_-]+", "-", result).strip("-")
        return (result or f"ticket-{ticket['ticket_number']}")[:100]

    def record_message(self, ticket: dict[str, Any], message_id: int | None, author_id: int | None, author_name: str, content: str,
                       attachments: list[dict[str, Any]], *, kind: str = "message", created_at: int | None = None, delivery_key: str | None = None) -> int:
        encrypted = self.transcripts.encrypt_text(content) if content else None
        metadata = {"attachments": [{"id": item.get("id"), "filename": str(item.get("filename", ""))[:255], "content_type": str(item.get("content_type") or "")[:100],
                                      "size": min(int(item.get("size", 0)), 2 ** 31 - 1), "stored": bool(item.get("stored"))} for item in attachments[:10]]}
        if delivery_key is not None:
            metadata['delivery_key'] = delivery_key
        message_row = self.repository.record_message(ticket["id"], message_id, author_id, author_name, encrypted, metadata, kind=kind, created_at=created_at)
        if kind not in {"note", "system"}:
            self.schedule_ticket(self.repository.ticket(int(ticket["id"])) or ticket)
        return message_row

    def schedule_ticket(self, ticket: dict[str, Any]) -> None:
        if ticket.get("status") != "open" or ticket.get("auto_close_excluded"):
            self.repository.set_schedule(int(ticket["id"]), "no_user_reply", None)
            self.repository.set_schedule(int(ticket["id"]), "inactivity", None)
            return
        settings = self.repository.settings(int(ticket["guild_id"]))
        panel = self.repository.panel(int(ticket["guild_id"]), int(ticket["panel_id"])) or {}
        auto = panel.get("auto_close") or settings["default_auto_close"]
        no_reply = int(auto.get("no_user_reply_minutes") or 0)
        inactivity = int(auto.get("inactivity_minutes") or 0)
        self.repository.set_schedule(int(ticket["id"]), "no_user_reply", None if ticket.get("last_user_message_at") or not no_reply else int(ticket.get("opened_at") or ticket["created_at"]) + no_reply * 60)
        self.repository.set_schedule(int(ticket["id"]), "inactivity", int(ticket.get("last_message_at") or ticket["created_at"]) + inactivity * 60 if inactivity else None)

    def queue_reply(self, ticket_id: int, actor_id: int, actor_name: str, content: str, *, anonymous: bool = False, note: bool = False) -> dict[str, Any]:
        ticket = self.repository.ticket(ticket_id)
        if not ticket or ticket["status"] not in {"open", "awaiting_user"}:
            raise TicketValidationError("ticket_closed", "開いているチケットではありません。")
        clean = content.strip()
        if not clean or len(clean) > 2000:
            raise TicketValidationError("message_invalid", "返信は1～2000文字で入力してください。")
        payload = {"content_encrypted": self.transcripts.encrypt_text(clean), "actor_name": actor_name[:100], "anonymous": bool(anonymous), "note": bool(note)}
        self.repository.audit(ticket["guild_id"], "note_queued" if note else "reply_queued", actor_id, ticket_id, {"anonymous": bool(anonymous)})
        return self.repository.queue_outbox(ticket_id, "note" if note else "reply", actor_id, payload)

    async def close(self, ticket_id: int, actor_id: int, reason: str) -> tuple[dict[str, Any], dict[str, Any]]:
        lease = ResourceLease(self.repository.database_url, 'ticket_close', ticket_id)
        return await lease.run(lambda owned: self._close_owned(ticket_id, actor_id, reason, owned))

    async def _close_owned(self, ticket_id: int, actor_id: int, reason: str, lease) -> tuple[dict[str, Any], dict[str, Any]]:
        ticket = self.repository.ticket(ticket_id)
        if not ticket or ticket["status"] not in {"open", "awaiting_user"}:
            raise TicketValidationError("ticket_closed", "開いているチケットではありません。")
        ticket = self.repository.begin_close(ticket_id, actor_id, reason, lease=lease)
        try:
            messages, cursor = [], 0
            while True:
                page = self.repository.messages(ticket_id, after=cursor, limit=500)
                if not page:
                    break
                for item in page:
                    messages.append({"id": item["id"], "discord_message_id": item.get("discord_message_id"), "author_id": item.get("author_id"),
                        "author": item.get("author_name"), "kind": item.get("kind"), "content": self.transcripts.decrypt_text(item.get("encrypted_content")),
                        "attachments": item.get("metadata", {}).get("attachments", []), "edited_at": item.get("edited_at"), "deleted_at": item.get("deleted_at"), "created_at": item["created_at"]})
                cursor = int(page[-1]["id"])
            answers = {key: self.transcripts.decrypt_text(value) for key, value in dict(ticket.get("form_answers") or {}).items()}
            attachments = [{"id": item["id"], "filename": item["filename"], "content_type": item.get("content_type"), "size": item["byte_size"]} for item in self.repository.attachments(ticket_id) if item.get("status") == "ready"]
            payload = {"version": 1, "close_revision": ticket['revision'], "ticket": {key: ticket.get(key) for key in ("id", "guild_id", "ticket_number", "panel_id", "opener_id", "mode", "created_at", "opened_at")},
                       "form_answers": answers, "closed_by": actor_id, "close_reason": reason[:1000], "closed_at": int(time.time()), "messages": messages}
            payload["attachments"] = attachments
            stored = await self.transcripts.save(ticket["guild_id"], ticket_id, payload)
            retention = self.repository.settings(ticket["guild_id"])["transcript_retention_days"]
            transcript = self.repository.save_transcript(ticket_id, stored.backend, stored.object_key, stored.content_hash, stored.byte_size, int(time.time()) + retention * 86400, lease=lease)
            closed = self.repository.close_ticket(ticket_id, actor_id, reason, lease=lease)
        except LostLease:
            raise
        except Exception:
            self.repository.cancel_close(ticket_id, lease=lease)
            raise
        self.repository.audit(ticket["guild_id"], "ticket_closed", actor_id, ticket_id, {"transcript_id": transcript["id"]})
        return closed, transcript
