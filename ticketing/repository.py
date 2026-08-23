"""SQLite repository for the Ticket V2 workflow."""
from __future__ import annotations

import json
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

from .models import default_panel, default_settings, validate_deployment, validate_form, validate_panel, validate_panel_bundle, validate_settings


JSON_FIELDS = {
    "role_ids_json": "role_ids", "user_ids_json": "user_ids", "admin_user_ids_json": "admin_user_ids",
    "fields_json": "fields", "config_json": "config", "panel_ids_json": "panel_ids",
    "form_answers_json": "form_answers", "metadata_json": "metadata", "payload_json": "payload",
    "answers_encrypted_json": "answers_encrypted",
}


class TicketRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _item(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = dict(row)
        for source, target in JSON_FIELDS.items():
            if source in value:
                fallback = "[]" if source in {"fields_json", "panel_ids_json", "role_ids_json", "user_ids_json", "admin_user_ids_json"} else "{}"
                try:
                    value[target] = json.loads(value.get(source) or fallback)
                except (TypeError, json.JSONDecodeError):
                    value[target] = [] if source.endswith("ids_json") or source in {"fields_json", "panel_ids_json"} else {}
        return value

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS ticket_guild_settings (
                    guild_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0, open_limit INTEGER NOT NULL DEFAULT 1,
                    language TEXT NOT NULL DEFAULT 'ja', log_channel_id INTEGER, transcript_channel_id INTEGER,
                    transcript_retention_days INTEGER NOT NULL DEFAULT 365, close_dm INTEGER NOT NULL DEFAULT 1,
                    default_auto_close_json TEXT NOT NULL DEFAULT '{}', revision INTEGER NOT NULL DEFAULT 1, updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ticket_staff_teams (
                    id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, name TEXT NOT NULL, role_ids_json TEXT NOT NULL DEFAULT '[]',
                    user_ids_json TEXT NOT NULL DEFAULT '[]', admin_user_ids_json TEXT NOT NULL DEFAULT '[]', notification_channel_id INTEGER,
                    enabled INTEGER NOT NULL DEFAULT 1, revision INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                    UNIQUE(guild_id,name)
                );
                CREATE TABLE IF NOT EXISTS ticket_forms (
                    id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, name TEXT NOT NULL, title TEXT NOT NULL,
                    fields_json TEXT NOT NULL DEFAULT '[]', revision INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                    UNIQUE(guild_id,name)
                );
                CREATE TABLE IF NOT EXISTS ticket_panels (
                    id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                    mode TEXT NOT NULL, form_id INTEGER, team_id INTEGER, category_id INTEGER, thread_parent_channel_id INTEGER,
                    staff_notification_channel_id INTEGER, config_json TEXT NOT NULL DEFAULT '{}', enabled INTEGER NOT NULL DEFAULT 1,
                    revision INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, UNIQUE(guild_id,name)
                );
                CREATE TABLE IF NOT EXISTS ticket_panel_messages (
                    id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, name TEXT NOT NULL, channel_id INTEGER NOT NULL, message_id INTEGER,
                    title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT '#5865F2',
                    panel_ids_json TEXT NOT NULL DEFAULT '[]', config_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'draft', last_error TEXT,
                    lease_owner TEXT, lease_until INTEGER, revision INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, UNIQUE(guild_id,name)
                );
                CREATE TABLE IF NOT EXISTS ticket_counters (guild_id INTEGER PRIMARY KEY, next_number INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS tickets_v2 (
                    id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, ticket_number INTEGER NOT NULL, panel_id INTEGER, opener_id INTEGER NOT NULL,
                    interaction_id TEXT, mode TEXT NOT NULL, discord_container_id INTEGER, parent_channel_id INTEGER, status TEXT NOT NULL DEFAULT 'creating',
                    claimed_by INTEGER, close_reason TEXT, closed_by INTEGER, form_answers_json TEXT NOT NULL DEFAULT '{}',
                    auto_close_excluded INTEGER NOT NULL DEFAULT 0, last_user_message_at INTEGER, last_message_at INTEGER,
                    notes_thread_id INTEGER, closing_at INTEGER, awaiting_return_category_id INTEGER, created_at INTEGER NOT NULL, opened_at INTEGER, closed_at INTEGER, deleted_at INTEGER, revision INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(guild_id,ticket_number), UNIQUE(interaction_id)
                );
                CREATE INDEX IF NOT EXISTS idx_tickets_v2_guild_status ON tickets_v2(guild_id,status,created_at);
                CREATE INDEX IF NOT EXISTS idx_tickets_v2_container ON tickets_v2(discord_container_id);
                CREATE TABLE IF NOT EXISTS ticket_participants (
                    ticket_id INTEGER NOT NULL, subject_type TEXT NOT NULL, subject_id INTEGER NOT NULL, access TEXT NOT NULL DEFAULT 'member',
                    added_by INTEGER, created_at INTEGER NOT NULL, PRIMARY KEY(ticket_id,subject_type,subject_id)
                );
                CREATE TABLE IF NOT EXISTS ticket_messages (
                    id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, discord_message_id INTEGER, author_id INTEGER, author_name TEXT,
                    kind TEXT NOT NULL DEFAULT 'message', encrypted_content TEXT, metadata_json TEXT NOT NULL DEFAULT '{}',
                    edited_at INTEGER, deleted_at INTEGER, created_at INTEGER NOT NULL, UNIQUE(ticket_id,discord_message_id)
                );
                CREATE INDEX IF NOT EXISTS idx_ticket_messages_cursor ON ticket_messages(ticket_id,id);
                CREATE TABLE IF NOT EXISTS ticket_attachments (
                    id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, discord_attachment_id INTEGER NOT NULL,
                    filename TEXT NOT NULL, content_type TEXT, byte_size INTEGER NOT NULL, backend TEXT NOT NULL,
                    object_key TEXT NOT NULL, content_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ready', created_at INTEGER NOT NULL,
                    UNIQUE(ticket_id,discord_attachment_id)
                );
                CREATE TABLE IF NOT EXISTS ticket_outbox (
                    id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, action TEXT NOT NULL, actor_id INTEGER NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                    available_at INTEGER NOT NULL, lease_owner TEXT, lease_until INTEGER, last_error TEXT, created_at INTEGER NOT NULL, completed_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_ticket_outbox_due ON ticket_outbox(status,available_at,lease_until);
                CREATE TABLE IF NOT EXISTS ticket_blacklist (
                    guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, reason TEXT, created_by INTEGER, created_at INTEGER NOT NULL,
                    PRIMARY KEY(guild_id,user_id)
                );
                CREATE TABLE IF NOT EXISTS ticket_on_call (
                    guild_id INTEGER NOT NULL, team_id INTEGER NOT NULL, user_id INTEGER NOT NULL, enabled_at INTEGER NOT NULL,
                    PRIMARY KEY(guild_id,team_id,user_id)
                );
                CREATE TABLE IF NOT EXISTS ticket_close_requests (
                    id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, requested_by INTEGER NOT NULL, reason TEXT, status TEXT NOT NULL DEFAULT 'pending',
                    expires_at INTEGER NOT NULL, resolved_by INTEGER, resolved_at INTEGER, created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ticket_tags (
                    id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, name TEXT NOT NULL, content TEXT NOT NULL,
                    created_by INTEGER, revision INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                    UNIQUE(guild_id,name)
                );
                CREATE TABLE IF NOT EXISTS ticket_feedback (
                    ticket_id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, rating INTEGER NOT NULL, comment_encrypted TEXT,
                    form_id INTEGER, answers_encrypted_json TEXT NOT NULL DEFAULT '{}', created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ticket_transcripts (
                    id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, version INTEGER NOT NULL DEFAULT 1, backend TEXT NOT NULL,
                    object_key TEXT NOT NULL, content_hash TEXT NOT NULL, byte_size INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'ready',
                    last_error TEXT, expires_at INTEGER NOT NULL, created_at INTEGER NOT NULL, UNIQUE(ticket_id,version)
                );
                CREATE TABLE IF NOT EXISTS ticket_schedules (
                    id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, kind TEXT NOT NULL, due_at INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT,
                    created_at INTEGER NOT NULL, completed_at INTEGER, UNIQUE(ticket_id,kind)
                );
                CREATE INDEX IF NOT EXISTS idx_ticket_schedules_due ON ticket_schedules(status,due_at);
                CREATE TABLE IF NOT EXISTS ticket_audit_events (
                    id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, ticket_id INTEGER, actor_id INTEGER, event_type TEXT NOT NULL,
                    detail_json TEXT NOT NULL DEFAULT '{}', created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ticket_orphans (
                    id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, ticket_id INTEGER, container_id INTEGER NOT NULL,
                    resource_type TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', reason TEXT,
                    created_at INTEGER NOT NULL, recovered_at INTEGER, UNIQUE(guild_id,container_id)
                );
                CREATE TABLE IF NOT EXISTS ticket_migrations (name TEXT PRIMARY KEY, completed_at INTEGER NOT NULL);
            """)
            self._add_column(connection, "tickets_v2", "notes_thread_id", "INTEGER")
            self._add_column(connection, "tickets_v2", "closing_at", "INTEGER")
            self._add_column(connection, "ticket_panel_messages", "lease_owner", "TEXT")
            self._add_column(connection, "ticket_panel_messages", "lease_until", "INTEGER")
            self._add_column(connection, "ticket_panel_messages", "config_json", "TEXT NOT NULL DEFAULT '{}'")
            self._add_column(connection, "ticket_panel_messages", "previous_channel_id", "INTEGER")
            self._add_column(connection, "ticket_panel_messages", "previous_message_id", "INTEGER")
            self._add_column(connection, "ticket_panels", "archived_at", "INTEGER")
            self._add_column(connection, "tickets_v2", "awaiting_return_category_id", "INTEGER")
            self._add_column(connection, "ticket_feedback", "form_id", "INTEGER")
            self._add_column(connection, "ticket_feedback", "answers_encrypted_json", "TEXT NOT NULL DEFAULT '{}'")
        self.migrate_legacy()
        self.recover_incomplete_closes()

    @staticmethod
    def _add_column(connection: sqlite3.Connection, table: str, name: str, definition: str) -> None:
        columns = {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        if name not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def settings(self, guild_id: int) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM ticket_guild_settings WHERE guild_id=?", (guild_id,)).fetchone()
        if not row:
            return default_settings()
        value = dict(row)
        value["enabled"] = bool(value["enabled"])
        value["close_dm"] = bool(value["close_dm"])
        value["default_auto_close"] = json.loads(value.pop("default_auto_close_json") or "{}")
        return validate_settings(value)

    def save_settings(self, guild_id: int, value: dict[str, Any], expected_revision: int | None = None) -> dict[str, Any]:
        normalized, now = validate_settings(value), int(time.time())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute("SELECT revision FROM ticket_guild_settings WHERE guild_id=?", (guild_id,)).fetchone()
            if current and expected_revision is not None and int(current["revision"]) != expected_revision:
                raise RuntimeError("revision_conflict")
            if current:
                connection.execute("""UPDATE ticket_guild_settings SET enabled=?,open_limit=?,language=?,log_channel_id=?,transcript_channel_id=?,
                    transcript_retention_days=?,close_dm=?,default_auto_close_json=?,revision=revision+1,updated_at=? WHERE guild_id=?""",
                    (int(normalized["enabled"]), normalized["open_limit"], normalized["language"], normalized["log_channel_id"],
                     normalized["transcript_channel_id"], normalized["transcript_retention_days"], int(normalized["close_dm"]),
                     json.dumps(normalized["default_auto_close"]), now, guild_id))
            else:
                connection.execute("""INSERT INTO ticket_guild_settings(guild_id,enabled,open_limit,language,log_channel_id,transcript_channel_id,
                    transcript_retention_days,close_dm,default_auto_close_json,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (guild_id, int(normalized["enabled"]), normalized["open_limit"], normalized["language"], normalized["log_channel_id"],
                     normalized["transcript_channel_id"], normalized["transcript_retention_days"], int(normalized["close_dm"]),
                     json.dumps(normalized["default_auto_close"]), now))
        return self.settings(guild_id)

    def _list(self, table: str, guild_id: int) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(f"SELECT * FROM {table} WHERE guild_id=? ORDER BY id", (guild_id,)).fetchall()
        return [self._item(row) or {} for row in rows]

    def teams(self, guild_id: int) -> list[dict[str, Any]]:
        return self._list("ticket_staff_teams", guild_id)

    def team(self, guild_id: int, team_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            return self._item(connection.execute("SELECT * FROM ticket_staff_teams WHERE guild_id=? AND id=?", (guild_id, team_id)).fetchone())

    def save_team(self, guild_id: int, value: dict[str, Any], team_id: int | None = None, expected_revision: int | None = None) -> dict[str, Any]:
        name = str(value.get("name", "")).strip()
        if not name or len(name) > 80:
            raise ValueError("team_name")
        role_ids = sorted(set(int(item) for item in value.get("role_ids", [])))
        user_ids = sorted(set(int(item) for item in value.get("user_ids", [])))
        admins = sorted(set(int(item) for item in value.get("admin_user_ids", [])))
        notification = int(value["notification_channel_id"]) if value.get("notification_channel_id") else None
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if team_id is None:
                team_id = int(connection.execute("""INSERT INTO ticket_staff_teams(guild_id,name,role_ids_json,user_ids_json,admin_user_ids_json,notification_channel_id,enabled,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?)""", (guild_id, name, json.dumps(role_ids), json.dumps(user_ids), json.dumps(admins), notification, int(value.get("enabled", True)), now, now)).lastrowid)
            else:
                current = connection.execute("SELECT revision FROM ticket_staff_teams WHERE guild_id=? AND id=?", (guild_id, team_id)).fetchone()
                if not current:
                    raise KeyError("team")
                if expected_revision is not None and int(current["revision"]) != expected_revision:
                    raise RuntimeError("revision_conflict")
                connection.execute("""UPDATE ticket_staff_teams SET name=?,role_ids_json=?,user_ids_json=?,admin_user_ids_json=?,notification_channel_id=?,enabled=?,revision=revision+1,updated_at=? WHERE guild_id=? AND id=?""",
                    (name, json.dumps(role_ids), json.dumps(user_ids), json.dumps(admins), notification, int(value.get("enabled", True)), now, guild_id, team_id))
        return self.team(guild_id, team_id) or {}

    def forms(self, guild_id: int) -> list[dict[str, Any]]:
        return self._list("ticket_forms", guild_id)

    def form(self, guild_id: int, form_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            return self._item(connection.execute("SELECT * FROM ticket_forms WHERE guild_id=? AND id=?", (guild_id, form_id)).fetchone())

    def save_form(self, guild_id: int, value: dict[str, Any], form_id: int | None = None, expected_revision: int | None = None) -> dict[str, Any]:
        normalized, now = validate_form(value), int(time.time())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if form_id is None:
                form_id = int(connection.execute("INSERT INTO ticket_forms(guild_id,name,title,fields_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    (guild_id, normalized["name"], normalized["title"], json.dumps(normalized["fields"], ensure_ascii=False), now, now)).lastrowid)
            else:
                current = connection.execute("SELECT revision FROM ticket_forms WHERE guild_id=? AND id=?", (guild_id, form_id)).fetchone()
                if not current:
                    raise KeyError("form")
                if expected_revision is not None and int(current["revision"]) != expected_revision:
                    raise RuntimeError("revision_conflict")
                connection.execute("UPDATE ticket_forms SET name=?,title=?,fields_json=?,revision=revision+1,updated_at=? WHERE guild_id=? AND id=?",
                    (normalized["name"], normalized["title"], json.dumps(normalized["fields"], ensure_ascii=False), now, guild_id, form_id))
        return self.form(guild_id, form_id) or {}

    def panels(self, guild_id: int) -> list[dict[str, Any]]:
        with self._connection() as connection:
            values = [self._item(row) or {} for row in connection.execute("SELECT * FROM ticket_panels WHERE guild_id=? AND archived_at IS NULL ORDER BY id", (guild_id,)).fetchall()]
        return [{**item, **dict(item.get("config") or {}), "enabled": bool(item.get("enabled"))} for item in values]

    def panel(self, guild_id: int, panel_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            item = self._item(connection.execute("SELECT * FROM ticket_panels WHERE guild_id=? AND id=?", (guild_id, panel_id)).fetchone())
        return {**item, **dict(item.get("config") or {}), "enabled": bool(item.get("enabled"))} if item else None

    def save_panel(self, guild_id: int, value: dict[str, Any], panel_id: int | None = None, expected_revision: int | None = None) -> dict[str, Any]:
        normalized, now = validate_panel(value), int(time.time())
        columns = {"name", "description", "mode", "form_id", "team_id", "category_id", "thread_parent_channel_id", "staff_notification_channel_id", "enabled", "revision"}
        config = {key: val for key, val in normalized.items() if key not in columns}
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for key, table in (("form_id", "ticket_forms"), ("team_id", "ticket_staff_teams")):
                if normalized.get(key) and not connection.execute(f"SELECT 1 FROM {table} WHERE guild_id=? AND id=?", (guild_id, normalized[key])).fetchone():
                    raise ValueError(key)
            if panel_id is None:
                panel_id = int(connection.execute("""INSERT INTO ticket_panels(guild_id,name,description,mode,form_id,team_id,category_id,thread_parent_channel_id,staff_notification_channel_id,config_json,enabled,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (guild_id, normalized["name"], normalized["description"], normalized["mode"], normalized["form_id"], normalized["team_id"], normalized["category_id"], normalized["thread_parent_channel_id"], normalized["staff_notification_channel_id"], json.dumps(config, ensure_ascii=False), int(normalized["enabled"]), now, now)).lastrowid)
            else:
                current = connection.execute("SELECT revision FROM ticket_panels WHERE guild_id=? AND id=?", (guild_id, panel_id)).fetchone()
                if not current:
                    raise KeyError("panel")
                if expected_revision is not None and int(current["revision"]) != expected_revision:
                    raise RuntimeError("revision_conflict")
                connection.execute("""UPDATE ticket_panels SET name=?,description=?,mode=?,form_id=?,team_id=?,category_id=?,thread_parent_channel_id=?,staff_notification_channel_id=?,config_json=?,enabled=?,revision=revision+1,updated_at=? WHERE guild_id=? AND id=?""",
                    (normalized["name"], normalized["description"], normalized["mode"], normalized["form_id"], normalized["team_id"], normalized["category_id"], normalized["thread_parent_channel_id"], normalized["staff_notification_channel_id"], json.dumps(config, ensure_ascii=False), int(normalized["enabled"]), now, guild_id, panel_id))
        return self.panel(guild_id, panel_id) or {}

    def panel_messages(self, guild_id: int) -> list[dict[str, Any]]:
        return [{**item, **dict(item.get("config") or {})} for item in self._list("ticket_panel_messages", guild_id)]

    def panel_message(self, guild_id: int, message_config_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            item = self._item(connection.execute("SELECT * FROM ticket_panel_messages WHERE guild_id=? AND id=?", (guild_id, message_config_id)).fetchone())
        return {**item, **dict(item.get("config") or {})} if item else None

    def save_panel_message(self, guild_id: int, value: dict[str, Any], message_config_id: int | None = None, expected_revision: int | None = None) -> dict[str, Any]:
        panel_ids = [int(item) for item in value.get("panel_ids", [])]
        if not panel_ids or len(panel_ids) > 25 or len(set(panel_ids)) != len(panel_ids):
            raise ValueError("panel_ids")
        deployment = validate_deployment(value)
        name, title, description = deployment["name"], deployment["title"], deployment["description"]
        channel_id, color = int(deployment["channel_id"] or 0), deployment["color"]
        if channel_id <= 0:
            raise ValueError("panel_message")
        config = {key: deployment[key] for key in ("content", "image_url", "thumbnail_url")}
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            count = connection.execute(f"SELECT COUNT(*) FROM ticket_panels WHERE guild_id=? AND id IN ({','.join('?' for _ in panel_ids)})", (guild_id, *panel_ids)).fetchone()[0]
            if count != len(panel_ids):
                raise ValueError("panel_ids")
            if message_config_id is None:
                message_config_id = int(connection.execute("INSERT INTO ticket_panel_messages(guild_id,name,channel_id,title,description,color,panel_ids_json,config_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (guild_id, name, channel_id, title, description, color, json.dumps(panel_ids), json.dumps(config), now, now)).lastrowid)
            else:
                current = connection.execute("SELECT revision FROM ticket_panel_messages WHERE guild_id=? AND id=?", (guild_id, message_config_id)).fetchone()
                if not current:
                    raise KeyError("panel_message")
                if expected_revision is not None and int(current["revision"]) != expected_revision:
                    raise RuntimeError("revision_conflict")
                current_full = connection.execute("SELECT channel_id,message_id FROM ticket_panel_messages WHERE guild_id=? AND id=?", (guild_id, message_config_id)).fetchone()
                moving = int(current_full["channel_id"]) != channel_id and current_full["message_id"] is not None
                connection.execute("UPDATE ticket_panel_messages SET name=?,channel_id=?,title=?,description=?,color=?,panel_ids_json=?,config_json=?,previous_channel_id=?,previous_message_id=?,status='draft',revision=revision+1,updated_at=? WHERE guild_id=? AND id=?",
                    (name, channel_id, title, description, color, json.dumps(panel_ids), json.dumps(config), current_full["channel_id"] if moving else None, current_full["message_id"] if moving else None, now, guild_id, message_config_id))
            row = connection.execute("SELECT * FROM ticket_panel_messages WHERE id=?", (message_config_id,)).fetchone()
        item = self._item(row) or {}
        return {**item, **dict(item.get("config") or {})}

    def panel_bundle(self, guild_id: int, panel_id: int) -> dict[str, Any] | None:
        panel = self.panel(guild_id, panel_id)
        if not panel:
            return None
        deployments = [item for item in self.panel_messages(guild_id) if panel_id in [int(value) for value in item.get("panel_ids", [])]]
        return {"panel": panel, "deployment": deployments[0] if deployments else None, "deployments": deployments,
                "welcome_embed": panel["welcome_embed"], "permissions": panel["creator_permissions"],
                "access_rules": panel["access_rules"], "support_hours": panel["support_hours"]}

    def save_panel_bundle(self, guild_id: int, value: dict[str, Any], panel_id: int | None = None) -> dict[str, Any]:
        normalized, now = validate_panel_bundle(value), int(time.time())
        panel, deployment = normalized["panel"], normalized["deployment"]
        expected_panel_revision = int(value.get("panel", {}).get("revision")) if value.get("panel", {}).get("revision") else None
        columns = {"name", "description", "mode", "form_id", "team_id", "category_id", "thread_parent_channel_id", "staff_notification_channel_id", "enabled", "revision"}
        config = {key: val for key, val in panel.items() if key not in columns}
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for key, table in (("form_id", "ticket_forms"), ("exit_form_id", "ticket_forms"), ("team_id", "ticket_staff_teams")):
                if panel.get(key) and not connection.execute(f"SELECT 1 FROM {table} WHERE guild_id=? AND id=?", (guild_id, panel[key])).fetchone():
                    raise ValueError(key)
            if panel_id is None:
                panel_id = int(connection.execute("""INSERT INTO ticket_panels(guild_id,name,description,mode,form_id,team_id,category_id,thread_parent_channel_id,staff_notification_channel_id,config_json,enabled,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (guild_id, panel["name"], panel["description"], panel["mode"], panel["form_id"], panel["team_id"], panel["category_id"], panel["thread_parent_channel_id"], panel["staff_notification_channel_id"], json.dumps(config, ensure_ascii=False), int(panel["enabled"]), now, now)).lastrowid)
            else:
                current = connection.execute("SELECT revision FROM ticket_panels WHERE guild_id=? AND id=? AND archived_at IS NULL", (guild_id, panel_id)).fetchone()
                if not current:
                    raise KeyError("panel")
                if expected_panel_revision is not None and int(current["revision"]) != expected_panel_revision:
                    raise RuntimeError("revision_conflict")
                connection.execute("""UPDATE ticket_panels SET name=?,description=?,mode=?,form_id=?,team_id=?,category_id=?,thread_parent_channel_id=?,staff_notification_channel_id=?,config_json=?,enabled=?,revision=revision+1,updated_at=? WHERE guild_id=? AND id=?""",
                    (panel["name"], panel["description"], panel["mode"], panel["form_id"], panel["team_id"], panel["category_id"], panel["thread_parent_channel_id"], panel["staff_notification_channel_id"], json.dumps(config, ensure_ascii=False), int(panel["enabled"]), now, guild_id, panel_id))
            if deployment.get("panel_message_id"):
                message = connection.execute("SELECT * FROM ticket_panel_messages WHERE guild_id=? AND id=?", (guild_id, deployment["panel_message_id"])).fetchone()
                if not message:
                    raise ValueError("panel_message_id")
                if deployment.get("revision") is not None and int(message["revision"]) != int(deployment["revision"]):
                    raise RuntimeError("revision_conflict")
                panel_ids = json.loads(message["panel_ids_json"] or "[]")
                if panel_id not in panel_ids:
                    position = deployment.get("position")
                    panel_ids.insert(min(max(position if position is not None else len(panel_ids), 0), len(panel_ids)), panel_id)
                channel_id = deployment.get("channel_id") or int(message["channel_id"])
                moving = channel_id != int(message["channel_id"]) and message["message_id"] is not None
                message_config = {"content": deployment["content"], "image_url": deployment["image_url"], "thumbnail_url": deployment["thumbnail_url"]}
                connection.execute("""UPDATE ticket_panel_messages SET name=?,channel_id=?,title=?,description=?,color=?,panel_ids_json=?,config_json=?,previous_channel_id=?,previous_message_id=?,status='draft',last_error=NULL,revision=revision+1,updated_at=? WHERE id=?""",
                    (deployment["name"] or message["name"], channel_id, deployment["title"] or message["title"], deployment["description"], deployment["color"], json.dumps(panel_ids), json.dumps(message_config), message["channel_id"] if moving else None, message["message_id"] if moving else None, now, message["id"]))
            elif deployment.get("channel_id"):
                deployment_name = deployment["name"] or f"{panel['name']} Panel"
                connection.execute("""INSERT INTO ticket_panel_messages(guild_id,name,channel_id,title,description,color,panel_ids_json,config_json,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""", (guild_id, deployment_name, deployment["channel_id"], deployment["title"], deployment["description"], deployment["color"], json.dumps([panel_id]), json.dumps({"content": deployment["content"], "image_url": deployment["image_url"], "thumbnail_url": deployment["thumbnail_url"]}), now, now))
        return self.panel_bundle(guild_id, panel_id) or {}

    def detach_panel(self, guild_id: int, panel_id: int, message_config_id: int) -> bool:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT panel_ids_json FROM ticket_panel_messages WHERE guild_id=? AND id=?", (guild_id, message_config_id)).fetchone()
            if not row:
                return False
            panel_ids = [int(value) for value in json.loads(row["panel_ids_json"] or "[]") if int(value) != panel_id]
            connection.execute("UPDATE ticket_panel_messages SET panel_ids_json=?,status=?,last_error=NULL,revision=revision+1,updated_at=? WHERE id=?",
                               (json.dumps(panel_ids), "draft" if panel_ids else "delete", int(time.time()), message_config_id))
        return True

    def archive_panel(self, guild_id: int, panel_id: int) -> bool:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute("UPDATE ticket_panels SET enabled=0,archived_at=?,revision=revision+1,updated_at=? WHERE guild_id=? AND id=? AND archived_at IS NULL", (now, now, guild_id, panel_id)).rowcount
            if changed:
                rows = connection.execute("SELECT id,panel_ids_json FROM ticket_panel_messages WHERE guild_id=?", (guild_id,)).fetchall()
                for row in rows:
                    panel_ids = [int(value) for value in json.loads(row["panel_ids_json"] or "[]") if int(value) != panel_id]
                    if len(panel_ids) != len(json.loads(row["panel_ids_json"] or "[]")):
                        connection.execute("UPDATE ticket_panel_messages SET panel_ids_json=?,status=?,revision=revision+1,updated_at=? WHERE id=?", (json.dumps(panel_ids), "draft" if panel_ids else "delete", now, row["id"]))
        return bool(changed)

    def mark_panel_published(self, config_id: int, message_id: int, error: str | None = None, *, deleted: bool = False) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE ticket_panel_messages SET message_id=?,previous_channel_id=NULL,previous_message_id=NULL,status=?,last_error=?,lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?",
                               (message_id or None, "error" if error else ("detached" if deleted else "published"), error[:500] if error else None, int(time.time()), config_id))

    def claim_panel_messages(self, owner: str, limit: int = 5, lease_seconds: int = 60) -> list[dict[str, Any]]:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute("SELECT * FROM ticket_panel_messages WHERE status IN ('draft','delete') AND (lease_until IS NULL OR lease_until<?) ORDER BY id LIMIT ?", (now, max(1, min(limit, 25)))).fetchall()
            ids = [int(row["id"]) for row in rows]
            if ids:
                connection.execute(f"UPDATE ticket_panel_messages SET lease_owner=?,lease_until=? WHERE id IN ({','.join('?' for _ in ids)})", (owner, now + lease_seconds, *ids))
        return [{**(self._item(row) or {}), **dict((self._item(row) or {}).get("config") or {})} for row in rows]

    def reserve_ticket(self, guild_id: int, panel_id: int, opener_id: int, interaction_id: str, form_answers: dict[str, str], *, staff_exempt: bool = False) -> dict[str, Any]:
        now, settings = int(time.time()), self.settings(guild_id)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM tickets_v2 WHERE interaction_id=?", (interaction_id,)).fetchone()
            if existing:
                return self._item(existing) or {}
            panel = connection.execute("SELECT * FROM ticket_panels WHERE guild_id=? AND id=? AND enabled=1 AND archived_at IS NULL", (guild_id, panel_id)).fetchone()
            if not panel:
                raise KeyError("panel")
            panel_item = self._item(panel) or {}
            panel_config = {**default_panel(), **dict(panel_item.get("config") or {})}
            if not staff_exempt:
                count = connection.execute("SELECT COUNT(*) FROM tickets_v2 WHERE guild_id=? AND status IN ('creating','open','awaiting_user','closing')", (guild_id,)).fetchone()[0]
                if count >= settings["open_limit"]:
                    raise OverflowError("ticket_limit")
                user_count = connection.execute("SELECT COUNT(*) FROM tickets_v2 WHERE guild_id=? AND panel_id=? AND opener_id=? AND status IN ('creating','open','awaiting_user','closing')", (guild_id, panel_id, opener_id)).fetchone()[0]
                if user_count >= int(panel_config.get("per_user_open_limit", 1)):
                    raise OverflowError("user_ticket_limit")
                cooldown = int(panel_config.get("open_cooldown_seconds", 0))
                if cooldown:
                    last_opened = connection.execute("SELECT MAX(opened_at) FROM tickets_v2 WHERE guild_id=? AND panel_id=? AND opener_id=? AND opened_at IS NOT NULL", (guild_id, panel_id, opener_id)).fetchone()[0]
                    if last_opened and int(last_opened) + cooldown > now:
                        raise OverflowError(f"ticket_cooldown:{int(last_opened) + cooldown - now}")
            counter = connection.execute("SELECT next_number FROM ticket_counters WHERE guild_id=?", (guild_id,)).fetchone()
            number = int(counter["next_number"]) if counter else 1
            connection.execute("INSERT INTO ticket_counters(guild_id,next_number) VALUES(?,?) ON CONFLICT(guild_id) DO UPDATE SET next_number=excluded.next_number", (guild_id, number + 1))
            ticket_id = int(connection.execute("""INSERT INTO tickets_v2(guild_id,ticket_number,panel_id,opener_id,interaction_id,mode,form_answers_json,created_at,last_message_at)
                VALUES(?,?,?,?,?,?,?,?,?)""", (guild_id, number, panel_id, opener_id, interaction_id, panel["mode"], json.dumps(form_answers, ensure_ascii=False), now, now)).lastrowid)
            row = connection.execute("SELECT * FROM tickets_v2 WHERE id=?", (ticket_id,)).fetchone()
        return self._item(row) or {}

    def activate_ticket(self, ticket_id: int, container_id: int, parent_channel_id: int | None) -> dict[str, Any]:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("UPDATE tickets_v2 SET discord_container_id=?,parent_channel_id=?,status='open',opened_at=?,revision=revision+1 WHERE id=? AND status='creating'", (container_id, parent_channel_id, now, ticket_id))
        return self.ticket(ticket_id) or {}

    def fail_ticket(self, ticket_id: int, reason: str) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE tickets_v2 SET status='failed',close_reason=?,closed_at=?,revision=revision+1 WHERE id=? AND status='creating'", (reason[:500], int(time.time()), ticket_id))

    def record_orphan(self, guild_id: int, ticket_id: int, container_id: int, resource_type: str, reason: str) -> None:
        with self._connection() as connection:
            connection.execute("INSERT OR REPLACE INTO ticket_orphans(guild_id,ticket_id,container_id,resource_type,reason,created_at) VALUES(?,?,?,?,?,?)",
                               (guild_id, ticket_id, container_id, resource_type, reason[:500], int(time.time())))

    def ticket(self, ticket_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            return self._item(connection.execute("SELECT * FROM tickets_v2 WHERE id=?", (ticket_id,)).fetchone())

    def ticket_for_container(self, container_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            return self._item(connection.execute("SELECT * FROM tickets_v2 WHERE discord_container_id=? ORDER BY id DESC LIMIT 1", (container_id,)).fetchone())

    def tickets(self, guild_id: int, *, status: str | None = None, limit: int = 100, before: int | None = None) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM tickets_v2 WHERE guild_id=?", [guild_id]
        if status:
            query += " AND status=?"; params.append(status)
        if before:
            query += " AND id<?"; params.append(before)
        query += " ORDER BY id DESC LIMIT ?"; params.append(max(1, min(limit, 200)))
        with self._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._item(row) or {} for row in rows]

    def set_claim(self, ticket_id: int, actor_id: int | None, expected_revision: int | None = None) -> dict[str, Any]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute("SELECT mode,status,revision FROM tickets_v2 WHERE id=?", (ticket_id,)).fetchone()
            if not current or current["status"] not in {"open", "awaiting_user"} or current["mode"] != "channel":
                raise ValueError("claim_unavailable")
            if expected_revision is not None and int(current["revision"]) != expected_revision:
                raise RuntimeError("revision_conflict")
            connection.execute("UPDATE tickets_v2 SET claimed_by=?,revision=revision+1 WHERE id=?", (actor_id, ticket_id))
        return self.ticket(ticket_id) or {}

    def set_awaiting_user(self, ticket_id: int, return_category_id: int) -> dict[str, Any]:
        with self._connection() as connection:
            changed = connection.execute("UPDATE tickets_v2 SET status='awaiting_user',awaiting_return_category_id=?,revision=revision+1 WHERE id=? AND status='open'", (return_category_id, ticket_id)).rowcount
            if not changed:
                raise RuntimeError("ticket_not_open")
        return self.ticket(ticket_id) or {}

    def resume_awaiting_user(self, ticket_id: int) -> dict[str, Any]:
        with self._connection() as connection:
            changed = connection.execute("UPDATE tickets_v2 SET status='open',awaiting_return_category_id=NULL,revision=revision+1 WHERE id=? AND status='awaiting_user'", (ticket_id,)).rowcount
            if not changed:
                raise RuntimeError("ticket_not_awaiting")
        return self.ticket(ticket_id) or {}

    def set_notes_thread(self, ticket_id: int, thread_id: int) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE tickets_v2 SET notes_thread_id=?,revision=revision+1 WHERE id=? AND mode='channel'", (thread_id, ticket_id))

    def begin_close(self, ticket_id: int, actor_id: int, reason: str) -> dict[str, Any]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            result = connection.execute("UPDATE tickets_v2 SET status='closing',closing_at=?,closed_by=?,close_reason=?,revision=revision+1 WHERE id=? AND status IN ('open','awaiting_user')", (int(time.time()), actor_id, reason[:1000], ticket_id))
            if result.rowcount != 1:
                raise RuntimeError("ticket_not_open")
        return self.ticket(ticket_id) or {}

    def recover_incomplete_closes(self) -> None:
        with self._connection() as connection:
            connection.execute("""UPDATE tickets_v2 SET status=CASE WHEN EXISTS(
                SELECT 1 FROM ticket_transcripts tr WHERE tr.ticket_id=tickets_v2.id AND tr.status='ready'
            ) THEN 'closed' ELSE 'open' END,
            closed_at=CASE WHEN EXISTS(SELECT 1 FROM ticket_transcripts tr WHERE tr.ticket_id=tickets_v2.id AND tr.status='ready')
                THEN COALESCE(closed_at,(SELECT MAX(created_at) FROM ticket_transcripts tr WHERE tr.ticket_id=tickets_v2.id)) ELSE NULL END,
            closed_by=CASE WHEN EXISTS(SELECT 1 FROM ticket_transcripts tr WHERE tr.ticket_id=tickets_v2.id AND tr.status='ready') THEN closed_by ELSE NULL END,
            close_reason=CASE WHEN EXISTS(SELECT 1 FROM ticket_transcripts tr WHERE tr.ticket_id=tickets_v2.id AND tr.status='ready') THEN close_reason ELSE NULL END,
            closing_at=NULL,revision=revision+1 WHERE status='closing' AND (closing_at IS NULL OR closing_at<?)""", (int(time.time()) - 300,))

    def cancel_close(self, ticket_id: int) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE tickets_v2 SET status='open',closing_at=NULL,closed_by=NULL,close_reason=NULL,revision=revision+1 WHERE id=? AND status='closing'", (ticket_id,))

    def close_ticket(self, ticket_id: int, actor_id: int, reason: str) -> dict[str, Any]:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            result = connection.execute("UPDATE tickets_v2 SET status='closed',closing_at=NULL,closed_by=?,close_reason=?,closed_at=?,revision=revision+1 WHERE id=? AND status='closing'", (actor_id, reason[:1000], now, ticket_id))
            if result.rowcount != 1:
                raise RuntimeError("ticket_not_open")
            connection.execute("DELETE FROM ticket_schedules WHERE ticket_id=?", (ticket_id,))
        return self.ticket(ticket_id) or {}

    def reopen_ticket(self, ticket_id: int) -> dict[str, Any]:
        with self._connection() as connection:
            result = connection.execute("UPDATE tickets_v2 SET status='open',closed_by=NULL,close_reason=NULL,closed_at=NULL,revision=revision+1 WHERE id=? AND status='closed' AND mode='private_thread' AND deleted_at IS NULL", (ticket_id,))
            if result.rowcount != 1:
                raise ValueError("reopen_unavailable")
        return self.ticket(ticket_id) or {}

    def add_participant(self, ticket_id: int, subject_type: str, subject_id: int, actor_id: int, access: str = "member") -> None:
        if subject_type not in {"user", "role"} or access not in {"member", "staff"}:
            raise ValueError("participant")
        with self._connection() as connection:
            connection.execute("INSERT OR REPLACE INTO ticket_participants(ticket_id,subject_type,subject_id,access,added_by,created_at) VALUES(?,?,?,?,?,?)", (ticket_id, subject_type, subject_id, access, actor_id, int(time.time())))

    def remove_participant(self, ticket_id: int, subject_type: str, subject_id: int) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM ticket_participants WHERE ticket_id=? AND subject_type=? AND subject_id=?", (ticket_id, subject_type, subject_id))

    def create_close_request(self, ticket_id: int, actor_id: int, reason: str) -> dict[str, Any]:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("UPDATE ticket_close_requests SET status='expired' WHERE ticket_id=? AND status='pending' AND expires_at<=?", (ticket_id, now))
            existing = connection.execute("SELECT * FROM ticket_close_requests WHERE ticket_id=? AND status='pending'", (ticket_id,)).fetchone()
            if existing:
                return self._item(existing) or {}
            request_id = int(connection.execute("INSERT INTO ticket_close_requests(ticket_id,requested_by,reason,expires_at,created_at) VALUES(?,?,?,?,?)", (ticket_id, actor_id, reason[:1000], now + 86400, now)).lastrowid)
            row = connection.execute("SELECT * FROM ticket_close_requests WHERE id=?", (request_id,)).fetchone()
        return self._item(row) or {}

    def close_request(self, request_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            return self._item(connection.execute("SELECT * FROM ticket_close_requests WHERE id=?", (request_id,)).fetchone())

    def resolve_close_request(self, request_id: int, actor_id: int, approved: bool) -> dict[str, Any]:
        now = int(time.time())
        with self._connection() as connection:
            result = connection.execute("UPDATE ticket_close_requests SET status=?,resolved_by=?,resolved_at=? WHERE id=? AND status='pending' AND expires_at>?", ("approved" if approved else "denied", actor_id, now, request_id, now))
            if result.rowcount != 1:
                raise ValueError("close_request_unavailable")
            row = connection.execute("SELECT * FROM ticket_close_requests WHERE id=?", (request_id,)).fetchone()
        return self._item(row) or {}

    def expire_close_requests(self, now: int | None = None) -> int:
        with self._connection() as connection:
            return connection.execute("UPDATE ticket_close_requests SET status='expired' WHERE status='pending' AND expires_at<=?", (now or int(time.time()),)).rowcount

    def set_blacklist(self, guild_id: int, user_id: int, actor_id: int, reason: str | None) -> None:
        with self._connection() as connection:
            if reason is None:
                connection.execute("DELETE FROM ticket_blacklist WHERE guild_id=? AND user_id=?", (guild_id, user_id))
            else:
                connection.execute("INSERT OR REPLACE INTO ticket_blacklist(guild_id,user_id,reason,created_by,created_at) VALUES(?,?,?,?,?)", (guild_id, user_id, reason[:500], actor_id, int(time.time())))

    def set_on_call(self, guild_id: int, team_id: int, user_id: int, enabled: bool) -> None:
        with self._connection() as connection:
            if enabled:
                connection.execute("INSERT OR REPLACE INTO ticket_on_call(guild_id,team_id,user_id,enabled_at) VALUES(?,?,?,?)", (guild_id, team_id, user_id, int(time.time())))
            else:
                connection.execute("DELETE FROM ticket_on_call WHERE guild_id=? AND team_id=? AND user_id=?", (guild_id, team_id, user_id))

    def tags(self, guild_id: int) -> list[dict[str, Any]]:
        return self._list("ticket_tags", guild_id)

    def save_tag(self, guild_id: int, name: str, content: str, actor_id: int) -> dict[str, Any]:
        normalized = name.strip().lower()
        if not re.fullmatch(r"[a-z0-9_-]{1,40}", normalized) or not content.strip() or len(content) > 2000:
            raise ValueError("tag_invalid")
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("""INSERT INTO ticket_tags(guild_id,name,content,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?)
                ON CONFLICT(guild_id,name) DO UPDATE SET content=excluded.content,revision=revision+1,updated_at=excluded.updated_at""",
                (guild_id, normalized, content.strip(), actor_id, now, now))
            row = connection.execute("SELECT * FROM ticket_tags WHERE guild_id=? AND name=?", (guild_id, normalized)).fetchone()
        return self._item(row) or {}

    def delete_tag(self, guild_id: int, tag_id: int) -> bool:
        with self._connection() as connection:
            return connection.execute("DELETE FROM ticket_tags WHERE guild_id=? AND id=?", (guild_id, tag_id)).rowcount == 1

    def statistics(self, guild_id: int) -> dict[str, Any]:
        with self._connection() as connection:
            rows = connection.execute("""SELECT p.id,p.name,COUNT(t.id) total,
                SUM(CASE WHEN t.status='open' THEN 1 ELSE 0 END) open,
                SUM(CASE WHEN t.status='closed' THEN 1 ELSE 0 END) closed,
                AVG(CASE WHEN t.closed_at IS NOT NULL THEN t.closed_at-t.created_at END) average_resolution_seconds
                FROM ticket_panels p LEFT JOIN tickets_v2 t ON t.panel_id=p.id WHERE p.guild_id=? GROUP BY p.id,p.name ORDER BY total DESC""", (guild_id,)).fetchall()
        return {"summary": self.summary(guild_id), "panels": [dict(row) for row in rows]}

    def record_message(self, ticket_id: int, discord_message_id: int | None, author_id: int | None, author_name: str, encrypted_content: str | None,
                       metadata: dict[str, Any], *, kind: str = "message", created_at: int | None = None) -> int:
        now = created_at or int(time.time())
        with self._connection() as connection:
            cursor = connection.execute("""INSERT INTO ticket_messages(ticket_id,discord_message_id,author_id,author_name,kind,encrypted_content,metadata_json,created_at)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(ticket_id,discord_message_id) DO UPDATE SET author_id=excluded.author_id,author_name=excluded.author_name,
                encrypted_content=excluded.encrypted_content,metadata_json=excluded.metadata_json,edited_at=excluded.created_at""",
                (ticket_id, discord_message_id, author_id, author_name[:100], kind, encrypted_content, json.dumps(metadata, ensure_ascii=False), now))
            connection.execute("UPDATE tickets_v2 SET last_message_at=?,last_user_message_at=CASE WHEN opener_id=? THEN ? ELSE last_user_message_at END WHERE id=?", (now, author_id, now, ticket_id))
        return int(cursor.lastrowid or 0)

    def mark_message_deleted(self, discord_message_id: int) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE ticket_messages SET deleted_at=? WHERE discord_message_id=?", (int(time.time()), discord_message_id))

    def messages(self, ticket_id: int, *, after: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM ticket_messages WHERE ticket_id=? AND id>? ORDER BY id LIMIT ?", (ticket_id, after, max(1, min(limit, 500)))).fetchall()
        return [self._item(row) or {} for row in rows]

    def attachment_usage(self, ticket_id: int) -> int:
        with self._connection() as connection:
            return int(connection.execute("SELECT COALESCE(SUM(byte_size),0) FROM ticket_attachments WHERE ticket_id=? AND status='ready'", (ticket_id,)).fetchone()[0])

    def save_attachment(self, ticket_id: int, discord_attachment_id: int, filename: str, content_type: str | None, byte_size: int,
                        backend: str, object_key: str, content_hash: str) -> dict[str, Any]:
        with self._connection() as connection:
            connection.execute("""INSERT OR IGNORE INTO ticket_attachments(ticket_id,discord_attachment_id,filename,content_type,byte_size,backend,object_key,content_hash,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""", (ticket_id, discord_attachment_id, filename[:255], (content_type or "")[:100], byte_size, backend, object_key, content_hash, int(time.time())))
            row = connection.execute("SELECT * FROM ticket_attachments WHERE ticket_id=? AND discord_attachment_id=?", (ticket_id, discord_attachment_id)).fetchone()
        return self._item(row) or {}

    def attachments(self, ticket_id: int) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM ticket_attachments WHERE ticket_id=? ORDER BY id", (ticket_id,)).fetchall()
        return [self._item(row) or {} for row in rows]

    def attachment(self, attachment_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT a.*,t.guild_id,t.opener_id,t.panel_id FROM ticket_attachments a JOIN tickets_v2 t ON t.id=a.ticket_id WHERE a.id=?", (attachment_id,)).fetchone()
        return self._item(row)

    def local_attachments(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM ticket_attachments WHERE backend='local' AND status='ready' ORDER BY id LIMIT ?", (max(1, min(limit, 100)),)).fetchall()
        return [self._item(row) or {} for row in rows]

    def mark_attachment_promoted(self, attachment_id: int) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE ticket_attachments SET backend='s3' WHERE id=? AND backend='local'", (attachment_id,))

    def transcript_for_ticket(self, ticket_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT tr.*,t.guild_id,t.opener_id,t.panel_id FROM ticket_transcripts tr JOIN tickets_v2 t ON t.id=tr.ticket_id WHERE tr.ticket_id=? ORDER BY tr.version DESC LIMIT 1", (ticket_id,)).fetchone()
        return self._item(row)

    def local_transcripts(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM ticket_transcripts WHERE backend='local' AND status='ready' ORDER BY id LIMIT ?", (max(1, min(limit, 100)),)).fetchall()
        return [self._item(row) or {} for row in rows]

    def mark_transcript_promoted(self, transcript_id: int) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE ticket_transcripts SET backend='s3',last_error=NULL WHERE id=? AND backend='local'", (transcript_id,))

    def expired_transcripts(self, now: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM ticket_transcripts WHERE status='ready' AND expires_at<=? ORDER BY expires_at LIMIT ?", (now or int(time.time()), max(1, min(limit, 200)))).fetchall()
        return [self._item(row) or {} for row in rows]

    def mark_transcript_deleted(self, transcript_id: int, ticket_id: int) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("UPDATE ticket_transcripts SET status='deleted',last_error=NULL WHERE id=?", (transcript_id,))
            connection.execute("UPDATE ticket_messages SET encrypted_content=NULL WHERE ticket_id=?", (ticket_id,))
            connection.execute("UPDATE tickets_v2 SET form_answers_json='{}' WHERE id=?", (ticket_id,))
            connection.execute("UPDATE ticket_attachments SET status='deleted' WHERE ticket_id=?", (ticket_id,))

    def legacy_plaintext_transcripts(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connection() as connection:
            tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "support_tickets" not in tables:
                return []
            rows = connection.execute("""SELECT legacy.channel_id,legacy.transcript_json,v2.* FROM support_tickets legacy
                JOIN tickets_v2 v2 ON v2.discord_container_id=legacy.channel_id
                LEFT JOIN ticket_transcripts tr ON tr.ticket_id=v2.id
                WHERE legacy.transcript_json IS NOT NULL AND legacy.transcript_json<>'' AND tr.id IS NULL LIMIT ?""", (max(1, min(limit, 100)),)).fetchall()
        return [self._item(row) or {} for row in rows]

    def clear_legacy_transcript(self, channel_id: int) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE support_tickets SET transcript_json=NULL WHERE channel_id=?", (channel_id,))

    def queue_outbox(self, ticket_id: int, action: str, actor_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time())
        with self._connection() as connection:
            if action in {"close", "auto_close"}:
                existing = connection.execute("SELECT * FROM ticket_outbox WHERE ticket_id=? AND action IN ('close','auto_close') AND status IN ('pending','retry','processing') ORDER BY id LIMIT 1", (ticket_id,)).fetchone()
                if existing:
                    return self._item(existing) or {}
            outbox_id = int(connection.execute("INSERT INTO ticket_outbox(ticket_id,action,actor_id,payload_json,available_at,created_at) VALUES(?,?,?,?,?,?)",
                (ticket_id, action, actor_id, json.dumps(payload, ensure_ascii=False), now, now)).lastrowid)
            row = connection.execute("SELECT * FROM ticket_outbox WHERE id=?", (outbox_id,)).fetchone()
        return self._item(row) or {}

    def claim_outbox(self, owner: str, limit: int = 20, lease_seconds: int = 60) -> list[dict[str, Any]]:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute("SELECT * FROM ticket_outbox WHERE status IN ('pending','retry') AND available_at<=? AND (lease_until IS NULL OR lease_until<?) ORDER BY id LIMIT ?", (now, now, max(1, min(limit, 100)))).fetchall()
            ids = [int(row["id"]) for row in rows]
            if ids:
                connection.execute(f"UPDATE ticket_outbox SET status='processing',lease_owner=?,lease_until=?,attempts=attempts+1 WHERE id IN ({','.join('?' for _ in ids)})", (owner, now + lease_seconds, *ids))
        return [self._item(row) or {} for row in rows]

    def outbox(self, ticket_id: int, limit: int = 50) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT id,action,actor_id,status,attempts,last_error,created_at,completed_at FROM ticket_outbox WHERE ticket_id=? ORDER BY id DESC LIMIT ?", (ticket_id, max(1, min(limit, 100)))).fetchall()
        return [dict(row) for row in rows]

    def complete_outbox(self, outbox_id: int, owner: str, error: str | None = None, retry: bool = True) -> None:
        now = int(time.time())
        with self._connection() as connection:
            if error:
                row = connection.execute("SELECT attempts FROM ticket_outbox WHERE id=? AND lease_owner=?", (outbox_id, owner)).fetchone()
                attempts = int(row["attempts"] if row else 1)
                delay = min(3600, 15 * 2 ** min(attempts, 8)) if retry else 0
                connection.execute("UPDATE ticket_outbox SET status=?,available_at=?,last_error=?,lease_owner=NULL,lease_until=NULL WHERE id=? AND lease_owner=?", ("retry" if retry else "failed", now + delay, error[:500], outbox_id, owner))
            else:
                connection.execute("UPDATE ticket_outbox SET status='completed',completed_at=?,last_error=NULL,lease_owner=NULL,lease_until=NULL WHERE id=? AND lease_owner=?", (now, outbox_id, owner))

    def set_schedule(self, ticket_id: int, kind: str, due_at: int | None) -> None:
        if kind not in {"no_user_reply", "inactivity"}:
            raise ValueError("schedule_kind")
        with self._connection() as connection:
            if due_at is None:
                connection.execute("DELETE FROM ticket_schedules WHERE ticket_id=? AND kind=?", (ticket_id, kind))
            else:
                connection.execute("""INSERT INTO ticket_schedules(ticket_id,kind,due_at,created_at) VALUES(?,?,?,?)
                    ON CONFLICT(ticket_id,kind) DO UPDATE SET due_at=excluded.due_at,status='pending',attempts=0,last_error=NULL,completed_at=NULL""",
                    (ticket_id, kind, due_at, int(time.time())))

    def due_schedules(self, now: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM ticket_schedules WHERE status='pending' AND due_at<=? ORDER BY due_at,id LIMIT ?", (now or int(time.time()), max(1, min(limit, 200)))).fetchall()
        return [self._item(row) or {} for row in rows]

    def complete_schedule(self, schedule_id: int) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE ticket_schedules SET status='completed',completed_at=? WHERE id=? AND status='pending'", (int(time.time()), schedule_id))

    def save_transcript(self, ticket_id: int, backend: str, object_key: str, content_hash: str, byte_size: int, expires_at: int) -> dict[str, Any]:
        now = int(time.time())
        with self._connection() as connection:
            version = int(connection.execute("SELECT COALESCE(MAX(version),0)+1 FROM ticket_transcripts WHERE ticket_id=?", (ticket_id,)).fetchone()[0])
            transcript_id = int(connection.execute("INSERT INTO ticket_transcripts(ticket_id,version,backend,object_key,content_hash,byte_size,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (ticket_id, version, backend, object_key, content_hash, byte_size, expires_at, now)).lastrowid)
            row = connection.execute("SELECT * FROM ticket_transcripts WHERE id=?", (transcript_id,)).fetchone()
        return self._item(row) or {}

    def transcript(self, transcript_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT tr.*,t.guild_id,t.opener_id,t.panel_id FROM ticket_transcripts tr JOIN tickets_v2 t ON t.id=tr.ticket_id WHERE tr.id=?", (transcript_id,)).fetchone()
        return self._item(row)

    def save_feedback(self, ticket_id: int, user_id: int, rating: int, comment_encrypted: str | None = None,
                      form_id: int | None = None, answers_encrypted: dict[str, str] | None = None) -> dict[str, Any]:
        if rating < 1 or rating > 5:
            raise ValueError("feedback_rating")
        with self._connection() as connection:
            ticket = connection.execute("SELECT guild_id,opener_id,status FROM tickets_v2 WHERE id=?", (ticket_id,)).fetchone()
            if not ticket or int(ticket["opener_id"]) != user_id or ticket["status"] != "closed":
                raise PermissionError("feedback_forbidden")
            connection.execute("INSERT INTO ticket_feedback(ticket_id,user_id,rating,comment_encrypted,form_id,answers_encrypted_json,created_at) VALUES(?,?,?,?,?,?,?)",
                               (ticket_id, user_id, rating, comment_encrypted, form_id, json.dumps(answers_encrypted or {}, ensure_ascii=False), int(time.time())))
            row = connection.execute("SELECT * FROM ticket_feedback WHERE ticket_id=?", (ticket_id,)).fetchone()
        return self._item(row) or {}

    def audit(self, guild_id: int, event_type: str, actor_id: int | None, ticket_id: int | None = None, detail: dict[str, Any] | None = None) -> None:
        with self._connection() as connection:
            connection.execute("INSERT INTO ticket_audit_events(guild_id,ticket_id,actor_id,event_type,detail_json,created_at) VALUES(?,?,?,?,?,?)",
                               (guild_id, ticket_id, actor_id, event_type, json.dumps(detail or {}, ensure_ascii=False), int(time.time())))

    def summary(self, guild_id: int) -> dict[str, Any]:
        with self._connection() as connection:
            open_count = connection.execute("SELECT COUNT(*) FROM tickets_v2 WHERE guild_id=? AND status IN ('creating','open','awaiting_user','closing')", (guild_id,)).fetchone()[0]
            unclaimed = connection.execute("SELECT COUNT(*) FROM tickets_v2 WHERE guild_id=? AND status='open' AND mode='channel' AND claimed_by IS NULL", (guild_id,)).fetchone()[0]
            closed_30d = connection.execute("SELECT COUNT(*) FROM tickets_v2 WHERE guild_id=? AND status='closed' AND closed_at>=?", (guild_id, int(time.time()) - 30 * 86400)).fetchone()[0]
            rating = connection.execute("SELECT AVG(f.rating) FROM ticket_feedback f JOIN tickets_v2 t ON t.id=f.ticket_id WHERE t.guild_id=?", (guild_id,)).fetchone()[0]
        return {"open": int(open_count), "unclaimed": int(unclaimed), "closed_30d": int(closed_30d), "average_rating": round(float(rating), 2) if rating is not None else None}

    def migrate_legacy(self) -> None:
        with self._connection() as connection:
            tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "guild_modules" not in tables or connection.execute("SELECT 1 FROM ticket_migrations WHERE name='legacy_ticket_v2'").fetchone():
                return
            connection.execute("BEGIN IMMEDIATE")
            modules = connection.execute("SELECT guild_id,enabled,settings_json FROM guild_modules WHERE module_id='tickets'").fetchall()
            now = int(time.time())
            for module in modules:
                guild_id, settings = int(module["guild_id"]), json.loads(module["settings_json"] or "{}")
                connection.execute("INSERT OR IGNORE INTO ticket_guild_settings(guild_id,enabled,log_channel_id,transcript_channel_id,updated_at) VALUES(?,?,?,?,?)",
                    (guild_id, int(module["enabled"]), settings.get("ticket_log_channel_id"), settings.get("ticket_log_channel_id"), now))
                team = connection.execute("SELECT id FROM ticket_staff_teams WHERE guild_id=? AND name='Default Staff'", (guild_id,)).fetchone()
                if not team:
                    team_id = int(connection.execute("INSERT INTO ticket_staff_teams(guild_id,name,role_ids_json,created_at,updated_at) VALUES(?,?,?,?,?)",
                        (guild_id, "Default Staff", json.dumps([settings["ticket_staff_role_id"]] if settings.get("ticket_staff_role_id") else []), now, now)).lastrowid)
                else:
                    team_id = int(team["id"])
                panel = connection.execute("SELECT id FROM ticket_panels WHERE guild_id=? AND name='Default Panel'", (guild_id,)).fetchone()
                if not panel and settings.get("ticket_category_id"):
                    config = default_panel(); config.update({"name": "Default Panel", "team_id": team_id, "category_id": settings.get("ticket_category_id")})
                    columns = {"name", "description", "mode", "form_id", "team_id", "category_id", "thread_parent_channel_id", "staff_notification_channel_id", "enabled", "revision"}
                    panel_id = int(connection.execute("""INSERT INTO ticket_panels(guild_id,name,description,mode,team_id,category_id,config_json,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?)""", (guild_id, config["name"], settings.get("ticket_panel_description") or config["description"], "channel", team_id, config["category_id"], json.dumps({key: val for key, val in config.items() if key not in columns}, ensure_ascii=False), now, now)).lastrowid)
                else:
                    panel_id = int(panel["id"]) if panel else None
                if panel_id and settings.get("ticket_panel_channel_id"):
                    connection.execute("INSERT OR IGNORE INTO ticket_panel_messages(guild_id,name,channel_id,title,description,panel_ids_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                        (guild_id, "Default Panel Message", settings["ticket_panel_channel_id"], settings.get("ticket_panel_title") or "サポートチケット", settings.get("ticket_panel_description") or "サポートが必要な場合はボタンを押してください。", json.dumps([panel_id]), now, now))
                if panel_id and "support_tickets" in tables:
                    for legacy in connection.execute("SELECT * FROM support_tickets WHERE guild_id=?", (guild_id,)).fetchall():
                        exists = connection.execute("SELECT 1 FROM tickets_v2 WHERE discord_container_id=?", (legacy["channel_id"],)).fetchone()
                        if exists:
                            continue
                        counter = connection.execute("SELECT COALESCE(MAX(ticket_number),0)+1 FROM tickets_v2 WHERE guild_id=?", (guild_id,)).fetchone()[0]
                        connection.execute("""INSERT INTO tickets_v2(guild_id,ticket_number,panel_id,opener_id,mode,discord_container_id,status,created_at,opened_at,closed_at,closed_by)
                            VALUES(?,?,?,?,? ,?,?,?,?,?,?)""", (guild_id, int(counter), panel_id, legacy["opener_id"], "channel", legacy["channel_id"], legacy["status"], legacy["created_at"], legacy["created_at"], legacy["closed_at"], legacy["closed_by"]))
            connection.execute("INSERT INTO ticket_migrations(name,completed_at) VALUES('legacy_ticket_v2',?)", (now,))
