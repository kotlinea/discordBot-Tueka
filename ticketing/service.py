"""Shared Ticket workflow service used by Discord and the dashboard."""
from __future__ import annotations

import re
import time
import json
from datetime import datetime
from typing import Any

from .models import support_is_open
from .repository import TicketRepository
from .transcripts import TranscriptStorage


class TicketValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class TicketService:
    def __init__(self, repository: TicketRepository, transcripts: TranscriptStorage) -> None:
        self.repository = repository
        self.transcripts = transcripts

    def validate_open(self, guild_id: int, panel_id: int, opener_id: int, role_ids: set[int], answers: dict[str, str] | None = None) -> tuple[dict[str, Any], dict[str, str]]:
        settings, panel = self.repository.settings(guild_id), self.repository.panel(guild_id, panel_id)
        if not settings["enabled"] or panel is None or not panel.get("enabled"):
            raise TicketValidationError("disabled", "チケット受付は現在利用できません。")
        required = set(int(item) for item in panel.get("required_role_ids", []))
        if required and not required.intersection(role_ids):
            raise TicketValidationError("panel_forbidden", "このチケットを作成する権限がありません。")
        with self.repository._connection() as connection:
            if connection.execute("SELECT 1 FROM ticket_blacklist WHERE guild_id=? AND user_id=?", (guild_id, opener_id)).fetchone():
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
                       attachments: list[dict[str, Any]], *, kind: str = "message", created_at: int | None = None) -> int:
        encrypted = self.transcripts.encrypt_text(content) if content else None
        metadata = {"attachments": [{"id": item.get("id"), "filename": str(item.get("filename", ""))[:255], "content_type": str(item.get("content_type") or "")[:100],
                                      "size": min(int(item.get("size", 0)), 2 ** 31 - 1), "stored": bool(item.get("stored"))} for item in attachments[:10]]}
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
        ticket = self.repository.ticket(ticket_id)
        if not ticket or ticket["status"] not in {"open", "awaiting_user"}:
            raise TicketValidationError("ticket_closed", "開いているチケットではありません。")
        ticket = self.repository.begin_close(ticket_id, actor_id, reason)
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
            payload = {"version": 1, "ticket": {key: ticket.get(key) for key in ("id", "guild_id", "ticket_number", "panel_id", "opener_id", "mode", "created_at", "opened_at")},
                       "form_answers": answers, "closed_by": actor_id, "close_reason": reason[:1000], "closed_at": int(time.time()), "messages": messages}
            payload["attachments"] = attachments
            stored = await self.transcripts.save(ticket["guild_id"], ticket_id, payload)
            retention = self.repository.settings(ticket["guild_id"])["transcript_retention_days"]
            transcript = self.repository.save_transcript(ticket_id, stored.backend, stored.object_key, stored.content_hash, stored.byte_size, int(time.time()) + retention * 86400)
            closed = self.repository.close_ticket(ticket_id, actor_id, reason)
        except Exception:
            self.repository.cancel_close(ticket_id)
            raise
        self.repository.audit(ticket["guild_id"], "ticket_closed", actor_id, ticket_id, {"transcript_id": transcript["id"]})
        return closed, transcript

    async def migrate_legacy_transcripts(self, limit: int = 20) -> int:
        if not self.transcripts.available:
            return 0
        migrated = 0
        for ticket in self.repository.legacy_plaintext_transcripts(limit):
            try:
                legacy = json.loads(str(ticket.get("transcript_json") or "[]"))
                if not isinstance(legacy, list):
                    raise ValueError("legacy transcript")
                payload = {"version": 1, "ticket": {key: ticket.get(key) for key in ("id", "guild_id", "ticket_number", "panel_id", "opener_id", "mode", "created_at", "opened_at")},
                           "form_answers": {}, "closed_by": ticket.get("closed_by"), "close_reason": ticket.get("close_reason") or "Legacy migration",
                           "closed_at": ticket.get("closed_at"), "messages": legacy}
                stored = await self.transcripts.save(int(ticket["guild_id"]), int(ticket["id"]), payload)
                # Verify decryption and integrity before deleting legacy plaintext.
                await self.transcripts.load(stored.backend, stored.object_key, stored.content_hash)
                retention = self.repository.settings(int(ticket["guild_id"]))["transcript_retention_days"]
                self.repository.save_transcript(int(ticket["id"]), stored.backend, stored.object_key, stored.content_hash, stored.byte_size, int(time.time()) + retention * 86400)
                self.repository.clear_legacy_transcript(int(ticket["channel_id"]))
                migrated += 1
            except Exception:
                continue
        return migrated
