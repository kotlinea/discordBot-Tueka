"""SQLite-backed storage shared by the bot and dashboard."""
import json
import sqlite3
import time
from pathlib import Path
from database import require_current, transaction
from typing import Any

from template_defaults import TEMPLATE_DEFAULTS
from suggestions import normalize_settings as normalize_suggestion_settings


class GuildStorage:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        require_current(self.database_path)

    def _connection(self):
        return transaction(self.database_path)

    def get_module(self, guild_id: int, module_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute("SELECT enabled, settings_json, revision FROM guild_modules WHERE guild_id = ? AND module_id = ?", (guild_id, module_id)).fetchone()
        if row:
            settings = json.loads(row["settings_json"])
            if module_id == "welcome":
                settings = self._welcome_settings(settings)
            elif module_id in {"live_stats", "temporary_voice"}:
                settings = self._template_module_settings(module_id, settings)
            elif module_id == "audit_log":
                settings = self._audit_log_settings(settings)
            elif module_id == "leveling":
                settings = self._leveling_settings(settings)
            elif module_id == "automod":
                settings = self._automod_settings(settings)
            elif module_id == "moderation":
                settings = self._moderation_settings(settings)
            elif module_id in {"anti_spam", "anti_raid", "infractions", "moderation_actions", "moderation_logs"}:
                settings = self._moderation_submodule_settings(module_id, settings)
            elif module_id == "suggestions":
                settings = normalize_suggestion_settings(settings)
            return {"enabled": bool(row["enabled"]), "settings": settings, "revision": int(row["revision"])}
        defaults = {"welcome": self._welcome_settings({}), "leveling": self._leveling_settings({}), "autorole": {"default_role_id": None}, "audit_log": self._audit_log_settings({}), "automod": self._automod_settings({}), "moderation": self._moderation_settings({}), "live_stats": self._template_module_settings("live_stats", {}), "temporary_voice": self._template_module_settings("temporary_voice", {}), "suggestions": normalize_suggestion_settings({})}.get(module_id, self._moderation_submodule_settings(module_id, {}) if module_id in {"anti_spam", "anti_raid", "infractions", "moderation_actions", "moderation_logs"} else {})
        return {"enabled": False, "settings": defaults, "revision": 0}

    @staticmethod
    def _welcome_settings(settings: dict[str, Any]) -> dict[str, Any]:
        """Apply defaults without silently enabling messages."""
        defaults = {
            "welcome_enabled": False,
            "welcome_channel_id": None,
            "welcome_format": "text",
            "welcome_content": TEMPLATE_DEFAULTS["welcome_content"],
            "leave_enabled": False,
            "leave_channel_id": None,
            "leave_format": "text",
            "leave_content": TEMPLATE_DEFAULTS["leave_content"],
        }
        defaults.update(settings)
        for field in ("welcome_content", "leave_content"):
            if not str(defaults.get(field) or "").strip():
                defaults[field] = TEMPLATE_DEFAULTS[field]
        if defaults["welcome_format"] not in {"text", "embed"}:
            defaults["welcome_format"] = "text"
        if defaults["leave_format"] not in {"text", "embed"}:
            defaults["leave_format"] = "text"
        return defaults

    @staticmethod
    def _template_module_settings(module_id: str, settings: dict[str, Any]) -> dict[str, Any]:
        defaults = {
            "live_stats": {"stats_channel_id": None, "stats_template": TEMPLATE_DEFAULTS["stats_template"]},
            "temporary_voice": {"temp_voice_trigger_id": None, "temp_voice_category_id": None, "temp_voice_name": TEMPLATE_DEFAULTS["temp_voice_name"]},
        }[module_id]
        defaults.update(settings)
        field = "stats_template" if module_id == "live_stats" else "temp_voice_name"
        if not str(defaults.get(field) or "").strip():
            defaults[field] = TEMPLATE_DEFAULTS[field]
        return defaults

    @staticmethod
    def _audit_log_settings(settings: dict[str, Any]) -> dict[str, Any]:
        """Apply explicit category defaults."""
        defaults: dict[str, Any] = {
            "management_channel_id": None,
            "log_message": False,
            "log_voice": False,
            "log_channel": False,
            "log_member": False,
            "log_role": False,
            "log_server": False,
        }
        defaults.update(settings)
        return defaults

    @staticmethod
    def _leveling_settings(settings: dict[str, Any]) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "text_notification_channel_id": None,
            "text_role_rewards": [],
            "voice_enabled": False,
            "voice_notification_channel_id": None,
            "voice_role_rewards": [],
            "voice_xp_per_minute": 5,
            "voice_allow_solo": False,
            "voice_allow_muted": False,
        }
        defaults.update(settings)
        return defaults

    @staticmethod
    def _automod_settings(settings: dict[str, Any]) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "log_channel_id": None,
            "immune_role_ids": [],
            "immune_user_ids": [],
            "immune_channel_ids": [],
            "evidence_excluded_channel_ids": [],
            "evidence_retention_days": 30,
            "point_thresholds": [],
            "rules_revision": 0,
        }
        defaults.update(settings)
        for key in ("immune_role_ids", "immune_user_ids", "immune_channel_ids", "evidence_excluded_channel_ids"):
            defaults[key] = list(dict.fromkeys(int(value) for value in defaults.get(key, []) if str(value).isdigit()))[:100]
        defaults["evidence_retention_days"] = max(1, min(int(defaults.get("evidence_retention_days", 30)), 365))
        return defaults

    @staticmethod
    def _moderation_settings(settings: dict[str, Any]) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "default_log_channel_id": None, "immune_role_ids": [], "immune_user_ids": [],
            "immune_channel_ids": [], "evidence_excluded_channel_ids": [], "evidence_retention_days": 30,
            "exclude_bots": True, "exclude_webhooks": True, "rules_revision": 0,
            "escalation_enabled": False, "escalation_threshold": 3, "escalation_action": "timeout",
            "escalation_timeout_minutes": 60, "dm_notify": False,
        }
        defaults.update(settings)
        for key in ("immune_role_ids", "immune_user_ids", "immune_channel_ids", "evidence_excluded_channel_ids"):
            defaults[key] = list(dict.fromkeys(int(value) for value in defaults.get(key, []) if str(value).isdigit()))[:100]
        defaults["evidence_retention_days"] = max(1, min(int(defaults.get("evidence_retention_days", 30)), 365))
        return defaults

    @staticmethod
    def _moderation_submodule_settings(module_id: str, settings: dict[str, Any]) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "log_channel_id": None, "immune_role_ids": [], "immune_user_ids": [], "immune_channel_ids": [],
        }
        if module_id == "infractions":
            defaults["point_thresholds"] = []
        elif module_id == "anti_raid":
            defaults.update({"default_lockdown_minutes": 30, "notify_channel_id": None})
        elif module_id == "moderation_logs":
            defaults.update({f"log_{name}": True for name in ("message_delete", "message_edit", "warning", "timeout", "kick", "ban", "unban", "join", "leave", "automod", "anti_spam", "anti_raid", "admin")})
        defaults.update(settings)
        for key in ("immune_role_ids", "immune_user_ids", "immune_channel_ids"):
            defaults[key] = list(dict.fromkeys(int(value) for value in defaults.get(key, []) if str(value).isdigit()))[:100]
        return defaults

    def set_module(self, guild_id: int, module_id: str, *, enabled: bool, settings: dict[str, Any] | None = None,
                   expected_revision: int | None = None) -> dict[str, Any]:
        current = self.get_module(guild_id, module_id)
        if expected_revision is not None and current["revision"] != expected_revision:
            raise RuntimeError("revision_conflict")
        values = current["settings"] if settings is None else settings
        with self._connection() as connection:
            connection.execute("""INSERT INTO guild_modules (guild_id, module_id, enabled, settings_json, revision) VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(guild_id, module_id) DO UPDATE SET enabled = excluded.enabled,
                settings_json = excluded.settings_json, revision = guild_modules.revision + 1""",
                (guild_id, module_id, int(enabled), json.dumps(values)))
        return self.get_module(guild_id, module_id)

    def module_enabled(self, guild_id: int, module_id: str) -> bool:
        return self.get_module(guild_id, module_id)["enabled"]


    @staticmethod
    def _moderation_rule(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        for column, key in (("trigger_config_json", "trigger_config"), ("conditions_json", "conditions"), ("exemptions_json", "exemptions"), ("actions_json", "actions")):
            value[key] = json.loads(value.pop(column))
        value["enabled"] = bool(value["enabled"])
        value["stop_on_match"] = bool(value["stop_on_match"])
        return value

    def moderation_rules(self, guild_id: int, *, family: str | None = None, enabled_only: bool = False) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM moderation_rules WHERE guild_id=?", [guild_id]
        if family:
            query, params = query + " AND family=?", [guild_id, family]
        if enabled_only:
            query += " AND enabled=1"
        query += " ORDER BY priority,id"
        with self._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._moderation_rule(row) for row in rows]

    def moderation_rule(self, guild_id: int, rule_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM moderation_rules WHERE guild_id=? AND id=?", (guild_id, rule_id)).fetchone()
        return self._moderation_rule(row) if row else None

    def next_moderation_rule_priority(self, guild_id: int, family: str) -> int:
        with self._connection() as connection:
            row = connection.execute("SELECT COALESCE(MAX(priority),0) AS value FROM moderation_rules WHERE guild_id=? AND family=?", (guild_id, family)).fetchone()
        return min(10000, int(row["value"]) + 10)

    def reorder_moderation_rules(self, guild_id: int, family: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not items or len(items) > 200:
            raise ValueError("Rule order must contain 1 to 200 rules")
        ids = [int(item.get("id", 0)) for item in items]
        if any(value <= 0 for value in ids) or len(ids) != len(set(ids)):
            raise ValueError("Rule order contains invalid or duplicate IDs")
        now = int(time.time())
        with self._connection() as connection:
            rows = connection.execute(f"SELECT id,revision FROM moderation_rules WHERE guild_id=? AND family=? AND id IN ({','.join('?' for _ in ids)})", (guild_id, family, *ids)).fetchall()
            current = {int(row["id"]): int(row["revision"]) for row in rows}
            if set(current) != set(ids):
                raise ValueError("Rule order contains a rule from another server or family")
            for position, item in enumerate(items, 1):
                rule_id = int(item["id"])
                if item.get("revision") is not None and int(item["revision"]) != current[rule_id]:
                    raise RuntimeError("revision_conflict")
                connection.execute("UPDATE moderation_rules SET priority=?,stop_on_match=?,revision=revision+1,updated_at=? WHERE guild_id=? AND family=? AND id=?",
                    (position * 10, int(bool(item.get("stop_on_match"))), now, guild_id, family, rule_id))
            core = connection.execute("SELECT enabled,settings_json FROM guild_modules WHERE guild_id=? AND module_id='moderation'", (guild_id,)).fetchone()
            settings = self._moderation_settings(json.loads(core["settings_json"]) if core else {})
            settings["rules_revision"] = int(settings.get("rules_revision", 0)) + 1
            connection.execute("""INSERT INTO guild_modules(guild_id,module_id,enabled,settings_json) VALUES(?,'moderation',?,?)
                ON CONFLICT(guild_id,module_id) DO UPDATE SET settings_json=excluded.settings_json""",
                (guild_id, int(core["enabled"]) if core else 0, json.dumps(settings)))
        return self.moderation_rules(guild_id, family=family)

    def save_moderation_rule(self, guild_id: int, rule: dict[str, Any], rule_id: int | None = None) -> dict[str, Any]:
        now = int(time.time())
        values = (rule["family"], rule["event_type"], str(rule["name"])[:100], int(bool(rule.get("enabled", True))),
            rule.get("mode", "enforce"), int(rule.get("priority", 100)), int(bool(rule.get("stop_on_match"))), rule["trigger_type"],
            json.dumps(rule.get("trigger_config", {}), ensure_ascii=False), json.dumps(rule.get("conditions", {})),
            json.dumps(rule.get("exemptions", {})), json.dumps(rule.get("actions", []), ensure_ascii=False))
        with self._connection() as connection:
            if rule_id is None:
                count = connection.execute("SELECT COUNT(*) AS count FROM moderation_rules WHERE guild_id=?", (guild_id,)).fetchone()["count"]
                if count >= 200:
                    raise ValueError("A server can have at most 200 Moderation rules")
                cursor = connection.execute("""INSERT INTO moderation_rules
                    (guild_id,family,event_type,name,enabled,mode,priority,stop_on_match,trigger_type,trigger_config_json,conditions_json,exemptions_json,actions_json,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (guild_id, *values, now, now))
                rule_id = int(cursor.lastrowid)
            else:
                cursor = connection.execute("""UPDATE moderation_rules SET family=?,event_type=?,name=?,enabled=?,mode=?,priority=?,stop_on_match=?,trigger_type=?,
                    trigger_config_json=?,conditions_json=?,exemptions_json=?,actions_json=?,revision=revision+1,updated_at=? WHERE guild_id=? AND id=?""",
                    (*values, now, guild_id, rule_id))
                if cursor.rowcount != 1:
                    raise ValueError("Moderation rule not found")
            row = connection.execute("SELECT * FROM moderation_rules WHERE guild_id=? AND id=?", (guild_id, rule_id)).fetchone()
            core = connection.execute("SELECT enabled,settings_json FROM guild_modules WHERE guild_id=? AND module_id='moderation'", (guild_id,)).fetchone()
            settings = self._moderation_settings(json.loads(core["settings_json"]) if core else {})
            settings["rules_revision"] = int(settings.get("rules_revision", 0)) + 1
            connection.execute("""INSERT INTO guild_modules(guild_id,module_id,enabled,settings_json) VALUES(?,'moderation',?,?)
                ON CONFLICT(guild_id,module_id) DO UPDATE SET settings_json=excluded.settings_json""",
                (guild_id, int(core["enabled"]) if core else 0, json.dumps(settings)))
        return self._moderation_rule(row)

    def delete_moderation_rule(self, guild_id: int, rule_id: int) -> bool:
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM moderation_rules WHERE guild_id=? AND id=?", (guild_id, rule_id))
            if cursor.rowcount:
                row = connection.execute("SELECT settings_json FROM guild_modules WHERE guild_id=? AND module_id='moderation'", (guild_id,)).fetchone()
                settings = self._moderation_settings(json.loads(row["settings_json"]) if row else {})
                settings["rules_revision"] = int(settings.get("rules_revision", 0)) + 1
                connection.execute("UPDATE guild_modules SET settings_json=? WHERE guild_id=? AND module_id='moderation'", (json.dumps(settings), guild_id))
        return bool(cursor.rowcount)

    def create_moderation_event(self, guild_id: int, *, family: str, event_type: str, source: str, reason: str,
            rule_id: int | None = None, actor_id: int | None = None, actor_kind: str = "human", target_user_id: int | None = None,
            channel_id: int | None = None, target_id: int | None = None, evidence_text: str | None = None,
            evidence: dict[str, Any] | None = None, mode: str = "enforce", retention_days: int = 30,
            dedupe_key: str | None = None) -> int | None:
        now = int(time.time())
        has_evidence = bool(evidence_text or evidence)
        expires = now + max(1, min(retention_days, 365)) * 86400 if has_evidence else None
        with self._connection() as connection:
            cursor = connection.execute("""INSERT OR IGNORE INTO moderation_events
                (guild_id,rule_id,family,event_type,source,actor_id,actor_kind,target_user_id,channel_id,target_id,reason,evidence_text,evidence_json,mode,created_at,evidence_expires_at,dedupe_key)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (guild_id,rule_id,family,event_type,source,actor_id,actor_kind,target_user_id,
                channel_id,target_id,reason,evidence_text[:1000] if evidence_text else None,json.dumps(evidence or {},ensure_ascii=False),mode,now,expires,dedupe_key))
        return int(cursor.lastrowid) if cursor.rowcount else None

    def finish_moderation_event(self, event_id: int, results: list[dict[str, Any]]) -> None:
        now = int(time.time())
        with self._connection() as connection:
            for sequence, result in enumerate(results):
                detail = {key: value for key, value in result.items() if key not in {"type", "status", "case_id"}}
                connection.execute("""INSERT OR REPLACE INTO moderation_action_results
                    (event_id,sequence,action_type,status,case_id,detail_json,created_at) VALUES(?,?,?,?,?,?,?)""",
                    (event_id,sequence,str(result.get("type","unknown")),str(result.get("status","unknown")),result.get("case_id"),json.dumps(detail,ensure_ascii=False),now))
            case_id = next((int(item["case_id"]) for item in results if item.get("case_id")), None)
            if case_id:
                connection.execute("UPDATE moderation_events SET case_id=? WHERE id=?", (case_id,event_id))

    def recent_moderation_events(self, guild_id: int, *, family: str | None = None, user_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM moderation_events WHERE guild_id=?", [guild_id]
        if family:
            query, params = query + " AND family=?", [*params, family]
        if user_id:
            query, params = query + " AND target_user_id=?", [*params, user_id]
        query += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        with self._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [{**dict(row), "evidence": json.loads(row["evidence_json"])} for row in rows]

    def moderation_summary(self, guild_id: int) -> dict[str, Any]:
        now = int(time.time())
        with self._connection() as connection:
            rules = {row["family"]: row["count"] for row in connection.execute("SELECT family,COUNT(*) count FROM moderation_rules WHERE guild_id=? AND enabled=1 GROUP BY family", (guild_id,)).fetchall()}
            events = connection.execute("SELECT COUNT(*) count FROM moderation_events WHERE guild_id=? AND created_at>?", (guild_id, now - 86400)).fetchone()["count"]
            lockdowns = connection.execute("SELECT COUNT(*) count FROM moderation_lockdowns WHERE guild_id=? AND status='active'", (guild_id,)).fetchone()["count"]
            sanctioned = connection.execute("SELECT COUNT(DISTINCT user_id) count FROM moderation_points WHERE guild_id=? AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>?)", (guild_id,now)).fetchone()["count"]
        return {"rules": rules, "events_24h": int(events), "active_lockdowns": int(lockdowns), "sanctioned_users": int(sanctioned)}

    def start_lockdown(self, guild_id: int, *, reason: str | None, started_by: int | None,
            unlock_at: int | None, source_event_id: int | None = None) -> int:
        with self._connection() as connection:
            existing = connection.execute("SELECT id FROM moderation_lockdowns WHERE guild_id=? AND status='active'", (guild_id,)).fetchone()
            if existing:
                return int(existing["id"])
            cursor = connection.execute("""INSERT INTO moderation_lockdowns
                (guild_id,source_event_id,reason,started_by,started_at,unlock_at) VALUES(?,?,?,?,?,?)""",
                (guild_id,source_event_id,reason,started_by,int(time.time()),unlock_at))
        return int(cursor.lastrowid)

    def save_lockdown_snapshot(self, lockdown_id: int, channel_id: int, role_id: int, before: dict[str, Any], applied: dict[str, Any]) -> None:
        with self._connection() as connection:
            connection.execute("""INSERT OR IGNORE INTO moderation_lockdown_snapshots
                (lockdown_id,channel_id,role_id,before_json,applied_json) VALUES(?,?,?,?,?)""",
                (lockdown_id,channel_id,role_id,json.dumps(before),json.dumps(applied)))

    def active_lockdown(self, guild_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM moderation_lockdowns WHERE guild_id=? AND status='active' ORDER BY id DESC LIMIT 1", (guild_id,)).fetchone()
        return dict(row) if row else None

    def due_lockdowns(self, now: int | None = None) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM moderation_lockdowns WHERE status='active' AND unlock_at IS NOT NULL AND unlock_at<=?", (int(time.time()) if now is None else now,)).fetchall()
        return [dict(row) for row in rows]

    def lockdown_snapshots(self, lockdown_id: int) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM moderation_lockdown_snapshots WHERE lockdown_id=? ORDER BY channel_id", (lockdown_id,)).fetchall()
        return [{**dict(row), "before": json.loads(row["before_json"]), "applied": json.loads(row["applied_json"])} for row in rows]

    def finish_lockdown(self, lockdown_id: int, *, error: str | None = None) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE moderation_lockdowns SET status=?,completed_at=?,last_error=? WHERE id=?",
                ("failed" if error else "completed", int(time.time()), error[:500] if error else None, lockdown_id))

    def set_raid_state(self, guild_id: int, active: bool, *, source_rule_id: int | None = None, lockdown_id: int | None = None) -> None:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("""INSERT INTO moderation_raid_state(guild_id,active,started_at,last_signal_at,source_rule_id,lockdown_id)
                VALUES(?,?,?,?,?,?) ON CONFLICT(guild_id) DO UPDATE SET active=excluded.active,
                started_at=CASE WHEN excluded.active=1 AND moderation_raid_state.active=0 THEN excluded.started_at ELSE moderation_raid_state.started_at END,
                last_signal_at=excluded.last_signal_at,source_rule_id=excluded.source_rule_id,lockdown_id=excluded.lockdown_id""",
                (guild_id,int(active),now if active else None,now,source_rule_id,lockdown_id))

    def stale_raid_states(self, quiet_before: int) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM moderation_raid_state WHERE active=1 AND last_signal_at<=? ORDER BY last_signal_at",
                (quiet_before,),
            ).fetchall()
        return [dict(row) for row in rows]


    def enqueue_moderation_action(self, guild_id: int, moderator_id: int, action: str, *, target_user_id: int | None = None,
            channel_id: int | None = None, reason: str | None = None, options: dict[str, Any] | None = None, dedupe_key: str) -> int | None:
        with self._connection() as connection:
            cursor = connection.execute("""INSERT OR IGNORE INTO moderation_action_requests
                (guild_id,moderator_id,target_user_id,channel_id,action,reason,options_json,created_at,dedupe_key)
                VALUES(?,?,?,?,?,?,?,?,?)""", (guild_id,moderator_id,target_user_id,channel_id,action,reason,json.dumps(options or {}),int(time.time()),dedupe_key))
        return int(cursor.lastrowid) if cursor.rowcount else None

    def pending_moderation_actions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM moderation_action_requests WHERE status='pending' ORDER BY id LIMIT ?", (max(1,min(limit,100)),)).fetchall()
        return [{**dict(row), "options": json.loads(row["options_json"])} for row in rows]

    def complete_moderation_request(self, request_id: int, *, result: dict[str, Any], failed: bool = False) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE moderation_action_requests SET status=?,completed_at=?,result_json=? WHERE id=? AND status='pending'",
                ("failed" if failed else "completed",int(time.time()),json.dumps(result,ensure_ascii=False),request_id))


    def active_points(self, guild_id: int, user_id: int, now: int | None = None) -> int:
        current = int(time.time()) if now is None else now
        with self._connection() as connection:
            row = connection.execute("""SELECT COALESCE(SUM(points),0) AS total FROM moderation_points
                WHERE guild_id=? AND user_id=? AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>?)""", (guild_id,user_id,current)).fetchone()
        return int(row["total"])

    def add_points(self, guild_id: int, user_id: int, points: int, reason: str | None, *, moderation_rule_id: int | None = None,
                   moderation_event_id: int | None = None, expires_at: int | None = None) -> tuple[int, int, int]:
        if not 1 <= points <= 1000:
            raise ValueError("Points must be between 1 and 1000")
        now = int(time.time())
        with self._connection() as connection:
            before = connection.execute("""SELECT COALESCE(SUM(points),0) AS total FROM moderation_points
                WHERE guild_id=? AND user_id=? AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>?)""", (guild_id,user_id,now)).fetchone()["total"]
            cursor = connection.execute("""INSERT INTO moderation_points
                (guild_id,user_id,points,reason,moderation_rule_id,moderation_event_id,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?)""",
                (guild_id,user_id,points,reason,moderation_rule_id,moderation_event_id,now,expires_at))
        return int(cursor.lastrowid), int(before), int(before) + points

    def revoke_points(self, guild_id: int, user_id: int) -> int:
        with self._connection() as connection:
            cursor = connection.execute("UPDATE moderation_points SET revoked_at=? WHERE guild_id=? AND user_id=? AND revoked_at IS NULL", (int(time.time()),guild_id,user_id))
        return cursor.rowcount

    def clear_warnings(self, guild_id: int, user_id: int) -> int:
        with self._connection() as connection:
            cursor = connection.execute("UPDATE moderation_points SET revoked_at=? WHERE guild_id=? AND user_id=? AND revoked_at IS NULL", (int(time.time()),guild_id,user_id))
        return cursor.rowcount

    def schedule_moderation_action(self, guild_id: int, user_id: int, action: str, due_at: int, reason: str | None, case_id: int | None) -> int:
        with self._connection() as connection:
            cursor = connection.execute("INSERT INTO scheduled_moderation_actions(guild_id,user_id,action,due_at,reason,case_id) VALUES(?,?,?,?,?,?)", (guild_id,user_id,action,due_at,reason,case_id))
        return int(cursor.lastrowid)

    def due_moderation_actions(self, now: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
        current = int(time.time()) if now is None else now
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM scheduled_moderation_actions WHERE completed_at IS NULL AND due_at<=? ORDER BY due_at LIMIT ?", (current,max(1,min(limit,500)))).fetchall()
        return [dict(row) for row in rows]

    def complete_moderation_action(self, action_id: int, error: str | None = None) -> None:
        with self._connection() as connection:
            if error:
                connection.execute("UPDATE scheduled_moderation_actions SET attempts=attempts+1,last_error=? WHERE id=?", (error[:500],action_id))
            else:
                connection.execute("UPDATE scheduled_moderation_actions SET attempts=attempts+1,completed_at=?,last_error=NULL WHERE id=?", (int(time.time()),action_id))


    def purge_moderation_evidence(self, now: int | None = None) -> int:
        with self._connection() as connection:
            cursor = connection.execute("UPDATE moderation_events SET evidence_text=NULL,evidence_json='{}',evidence_expires_at=NULL WHERE evidence_expires_at IS NOT NULL AND evidence_expires_at<=?", (int(time.time()) if now is None else now,))
        return cursor.rowcount


    def social_subscriptions(self, guild_id: int, provider: str | None = None) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM social_subscriptions WHERE guild_id=?", [guild_id]
        if provider:
            query += " AND provider=?"
            params.append(provider)
        query += " ORDER BY provider, account_name"
        with self._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._social_subscription_row(row) for row in rows]

    @staticmethod
    def _social_subscription_row(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["events"] = json.loads(value.pop("events_json"))
        value["event_channels"] = json.loads(value.pop("event_channels_json", "{}"))
        value["templates"] = json.loads(value.pop("templates_json", "{}"))
        return value

    def social_subscription(self, subscription_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM social_subscriptions WHERE id=?", (subscription_id,)).fetchone()
        return self._social_subscription_row(row) if row else None

    def matching_social_subscriptions(self, provider: str, account_id: str, event_type: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("""SELECT s.* FROM social_subscriptions s JOIN social_targets t ON t.id=s.target_id
                WHERE s.provider=? AND (s.account_id=? OR t.external_id=? OR t.account_key=?) AND s.enabled=1""",
                (provider, account_id, account_id, account_id.lower().lstrip("@"))).fetchall()
        return [self._social_subscription_row(row) for row in rows if event_type in json.loads(row["events_json"])]

    def ensure_social_target(self, provider: str, account_key: str) -> dict[str, Any]:
        if provider not in {"youtube", "twitch", "tiktok", "x", "instagram"} or not account_key:
            raise ValueError("Invalid social target")
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("""INSERT INTO social_targets(provider,account_key,handle,status,next_check_at,created_at,updated_at)
                VALUES(?,?,?,'pending',0,?,?) ON CONFLICT(provider,account_key) DO UPDATE SET updated_at=excluded.updated_at""",
                (provider, account_key, account_key, now, now))
            row = connection.execute("SELECT * FROM social_targets WHERE provider=? AND account_key=?", (provider, account_key)).fetchone()
        return self._social_target_row(row)

    @staticmethod
    def _social_target_row(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["cursor"] = json.loads(value.pop("cursor_json"))
        return value

    def social_target(self, target_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM social_targets WHERE id=?", (target_id,)).fetchone()
        return self._social_target_row(row) if row else None

    def social_targets(self, provider: str | None = None) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM social_targets", []
        if provider:
            query, params = query + " WHERE provider=?", [provider]
        with self._connection() as connection:
            rows = connection.execute(query + " ORDER BY id", params).fetchall()
        return [self._social_target_row(row) for row in rows]

    def save_social_subscription_v2(self, guild_id: int, provider: str, account_key: str, channel_id: int,
                                    events: list[str], event_channels: dict[str, int], templates: dict[str, Any],
                                    role_id: int | None = None, enabled: bool = True, *, subscription_id: int | None = None,
                                    expected_revision: int | None = None, max_count: int = 10) -> dict[str, Any]:
        target = self.ensure_social_target(provider, account_key)
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if subscription_id is None:
                count = connection.execute("SELECT COUNT(*) FROM social_subscriptions WHERE guild_id=? AND provider=?", (guild_id, provider)).fetchone()[0]
                if count >= max_count:
                    raise OverflowError("Provider account limit reached")
                try:
                    cursor = connection.execute("""INSERT INTO social_subscriptions
                        (guild_id,provider,account_id,account_name,channel_id,role_id,events_json,enabled,created_at,updated_at,target_id,event_channels_json,templates_json,status,revision)
                        VALUES(?,?,?,?,?,?, ?,?,?,?, ?,?,?, 'pending',1)""",
                        (guild_id, provider, account_key, account_key, channel_id, role_id, json.dumps(events), int(enabled), now, now,
                         target["id"], json.dumps(event_channels), json.dumps(templates, ensure_ascii=False)))
                    subscription_id = int(cursor.lastrowid)
                except sqlite3.IntegrityError as exc:
                    raise ValueError("Target is already registered") from exc
            else:
                current = connection.execute("SELECT revision FROM social_subscriptions WHERE id=? AND guild_id=?", (subscription_id, guild_id)).fetchone()
                if not current:
                    raise LookupError("Subscription not found")
                if expected_revision is not None and int(current["revision"]) != expected_revision:
                    raise RuntimeError("revision_conflict")
                connection.execute("""UPDATE social_subscriptions SET channel_id=?,role_id=?,events_json=?,event_channels_json=?,templates_json=?,enabled=?,updated_at=?,revision=revision+1
                    WHERE id=? AND guild_id=?""", (channel_id, role_id, json.dumps(events), json.dumps(event_channels), json.dumps(templates, ensure_ascii=False), int(enabled), now, subscription_id, guild_id))
            row = connection.execute("SELECT * FROM social_subscriptions WHERE id=?", (subscription_id,)).fetchone()
        return self._social_subscription_row(row)

    def request_social_target_retry(self, target_id: int) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE social_targets SET status='pending',last_error=NULL,next_check_at=0,lease_owner=NULL,lease_until=NULL,revision=revision+1,updated_at=? WHERE id=?", (int(time.time()), target_id))

    def wake_social_target(self, provider: str, account_id: str) -> int:
        with self._connection() as connection:
            result = connection.execute("""UPDATE social_targets SET next_check_at=0,updated_at=?
                WHERE provider=? AND (external_id=? OR account_key=?)""", (int(time.time()), provider, account_id, account_id))
        return int(result.rowcount)

    def invalidate_social_target(self, provider: str, account_id: str, error: str) -> int:
        now = int(time.time())
        with self._connection() as connection:
            rows = connection.execute("SELECT id,cursor_json FROM social_targets WHERE provider=? AND (external_id=? OR account_key=?)", (provider, account_id, account_id)).fetchall()
            for row in rows:
                cursor = json.loads(row["cursor_json"])
                cursor.pop("eventsub_synced_at", None)
                cursor.pop("websub_renew_at", None)
                connection.execute("UPDATE social_targets SET status='degraded',cursor_json=?,last_error=?,next_check_at=0,updated_at=? WHERE id=?",
                                   (json.dumps(cursor), error[:500], now, row["id"]))
                connection.execute("UPDATE social_subscriptions SET status='degraded',last_error=?,updated_at=? WHERE target_id=?", (error[:500], now, row["id"]))
        return len(rows)

    def claim_social_targets(self, owner: str, *, limit: int = 20, lease_seconds: int = 60) -> list[dict[str, Any]]:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute("""SELECT * FROM social_targets WHERE next_check_at<=? AND (lease_until IS NULL OR lease_until<?)
                AND (status='orphaned' OR EXISTS(SELECT 1 FROM social_subscriptions s WHERE s.target_id=social_targets.id AND s.enabled=1))
                ORDER BY next_check_at,id LIMIT ?""", (now, now, max(1, min(limit, 100)))).fetchall()
            ids = [int(row["id"]) for row in rows]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                connection.execute(f"UPDATE social_targets SET lease_owner=?,lease_until=? WHERE id IN ({placeholders})", (owner, now + lease_seconds, *ids))
        return [self._social_target_row(row) for row in rows]

    def complete_social_target(self, target_id: int, owner: str, *, status: str, cursor: dict[str, Any], next_check_at: int,
                               external_id: str | None = None, handle: str | None = None, display_name: str | None = None,
                               avatar_url: str | None = None, error: str | None = None) -> bool:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute("SELECT provider FROM social_targets WHERE id=? AND lease_owner=?", (target_id, owner)).fetchone()
            if not current:
                return False
            if external_id:
                canonical = connection.execute(
                    "SELECT id,status,last_error FROM social_targets WHERE provider=? AND external_id=? AND id<>? ORDER BY id LIMIT 1",
                    (current["provider"], external_id, target_id),
                ).fetchone()
                if canonical:
                    canonical_id = int(canonical["id"])
                    connection.execute("UPDATE social_subscriptions SET target_id=?,status=?,last_error=?,updated_at=? WHERE target_id=?",
                                       (canonical_id, canonical["status"], canonical["last_error"], now, target_id))
                    deleted = connection.execute("DELETE FROM social_targets WHERE id=? AND lease_owner=?", (target_id, owner))
                    return deleted.rowcount == 1
            cursor_result = connection.execute("""UPDATE social_targets SET external_id=COALESCE(?,external_id),handle=COALESCE(?,handle),
                display_name=COALESCE(?,display_name),avatar_url=COALESCE(?,avatar_url),status=?,cursor_json=?,last_error=?,last_checked_at=?,next_check_at=?,
                lease_owner=NULL,lease_until=NULL,revision=revision+1,updated_at=? WHERE id=? AND lease_owner=?""",
                (external_id, handle, display_name, avatar_url, status, json.dumps(cursor), error, now, next_check_at, now, target_id, owner))
            connection.execute("UPDATE social_subscriptions SET status=?,last_error=?,updated_at=? WHERE target_id=?", (status, error, now, target_id))
        return cursor_result.rowcount == 1

    def social_worker_heartbeat(self, worker_name: str, details: dict[str, Any] | None = None) -> None:
        with self._connection() as connection:
            connection.execute("""INSERT INTO social_worker_state(worker_name,heartbeat_at,details_json) VALUES(?,?,?)
                ON CONFLICT(worker_name) DO UPDATE SET heartbeat_at=excluded.heartbeat_at,details_json=excluded.details_json""",
                (worker_name, int(time.time()), json.dumps(details or {})))

    def social_worker_health(self) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM social_worker_state ORDER BY heartbeat_at DESC LIMIT 1").fetchone()
        return {**dict(row), "details": json.loads(row["details_json"])} if row else None

    def delete_social_subscription(self, guild_id: int, subscription_id: int) -> None:
        with self._connection() as connection:
            row = connection.execute("SELECT target_id FROM social_subscriptions WHERE guild_id=? AND id=?", (guild_id, subscription_id)).fetchone()
            connection.execute("DELETE FROM social_subscriptions WHERE guild_id=? AND id=?", (guild_id, subscription_id))
            if row and row["target_id"] is not None:
                remaining = connection.execute("SELECT COUNT(*) FROM social_subscriptions WHERE target_id=?", (row["target_id"],)).fetchone()[0]
                if not remaining:
                    connection.execute("UPDATE social_targets SET status='orphaned',next_check_at=0,lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?", (int(time.time()), row["target_id"]))

    def delete_social_target(self, target_id: int, owner: str) -> bool:
        with self._connection() as connection:
            result = connection.execute("DELETE FROM social_targets WHERE id=? AND lease_owner=? AND NOT EXISTS(SELECT 1 FROM social_subscriptions WHERE target_id=?)", (target_id, owner, target_id))
        return result.rowcount == 1

    def social_connection(self, guild_id: int, provider: str, account_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM social_connections WHERE guild_id=? AND provider=? AND account_id=?", (guild_id, provider, account_id)).fetchone()
        return dict(row) if row else None

    def social_connections(self, guild_id: int, provider: str | None = None) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM social_connections WHERE guild_id=?", [guild_id]
        if provider:
            query += " AND provider=?"
            params.append(provider)
        with self._connection() as connection:
            rows = connection.execute(query + " ORDER BY provider, account_name", params).fetchall()
        return [dict(row) for row in rows]

    def save_social_connection(self, guild_id: int, provider: str, account_id: str, account_name: str, access_token_encrypted: str, refresh_token_encrypted: str | None, expires_at: int | None) -> None:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("INSERT INTO social_connections(guild_id,provider,account_id,account_name,access_token_encrypted,refresh_token_encrypted,expires_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(guild_id,provider,account_id) DO UPDATE SET account_name=excluded.account_name,access_token_encrypted=excluded.access_token_encrypted,refresh_token_encrypted=excluded.refresh_token_encrypted,expires_at=excluded.expires_at,updated_at=excluded.updated_at", (guild_id, provider, account_id, account_name, access_token_encrypted, refresh_token_encrypted, expires_at, now, now))

    def create_social_oauth_state(self, state: str, guild_id: int, provider: str, *, ttl_seconds: int = 600) -> None:
        if provider not in {"tiktok", "instagram"}:
            raise ValueError("Unsupported social OAuth provider")
        with self._connection() as connection:
            connection.execute("DELETE FROM social_oauth_states WHERE expires_at < ?", (int(time.time()),))
            connection.execute("INSERT INTO social_oauth_states(state,guild_id,provider,expires_at) VALUES(?,?,?,?)", (state, guild_id, provider, int(time.time()) + ttl_seconds))

    def consume_social_oauth_state(self, state: str, provider: str) -> int | None:
        now = int(time.time())
        with self._connection() as connection:
            row = connection.execute("SELECT guild_id FROM social_oauth_states WHERE state=? AND provider=? AND expires_at>=?", (state, provider, now)).fetchone()
            connection.execute("DELETE FROM social_oauth_states WHERE state=?", (state,))
        return int(row["guild_id"]) if row else None

    def enqueue_social_event_v2(self, provider: str, external_event_id: str, account_id: str, event_type: str,
                                payload: dict[str, Any], *, occurred_at: int | None = None) -> bool:
        event_key = f"{provider}:{event_type}:{external_event_id}"
        now = int(time.time())
        with self._connection() as connection:
            cursor = connection.execute("""INSERT OR IGNORE INTO social_events
                (provider,event_key,account_id,payload_json,received_at,event_type,external_event_id,occurred_at,status,available_at)
                VALUES(?,?,?,?,?,?,?,?, 'pending',?)""",
                (provider, event_key, account_id, json.dumps(payload, ensure_ascii=False), now, event_type, external_event_id, occurred_at or now, now))
        return cursor.rowcount == 1

    def pending_social_events(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM social_events WHERE processed_at IS NULL AND available_at<=? ORDER BY id LIMIT 100", (int(time.time()),)).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def claim_social_events(self, owner: str, *, limit: int = 100, lease_seconds: int = 30) -> list[dict[str, Any]]:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute("""SELECT * FROM social_events WHERE processed_at IS NULL AND available_at<=?
                AND (lease_until IS NULL OR lease_until<?) ORDER BY id LIMIT ?""", (now, now, max(1, min(limit, 200)))).fetchall()
            ids = [int(row["id"]) for row in rows]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                connection.execute(f"UPDATE social_events SET lease_owner=?,lease_until=?,status='processing',attempts=attempts+1 WHERE id IN ({placeholders})", (owner, now + lease_seconds, *ids))
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def mark_social_event_processed(self, event_id: int) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE social_events SET processed_at=?,status='completed',lease_owner=NULL,lease_until=NULL WHERE id=?", (int(time.time()), event_id))

    def retry_social_event(self, event_id: int, error: str, *, delay_seconds: int = 30) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE social_events SET status='retry',available_at=?,last_error=?,lease_owner=NULL,lease_until=NULL WHERE id=?",
                               (int(time.time()) + max(1, delay_seconds), error[:500], event_id))

    def record_social_delivery(self, subscription_id: int, event_key: str, channel_id: int, message_id: int | None, state: str = "sent") -> bool:
        now = int(time.time())
        with self._connection() as connection:
            cursor = connection.execute("INSERT OR IGNORE INTO social_deliveries(subscription_id,event_key,discord_channel_id,discord_message_id,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (subscription_id, event_key, channel_id, message_id, state, now, now))
            if cursor.rowcount == 0:
                row = connection.execute("SELECT state,next_attempt_at FROM social_deliveries WHERE subscription_id=? AND event_key=?", (subscription_id, event_key)).fetchone()
                return bool(row and row["state"] in {"pending", "retry"} and int(row["next_attempt_at"] or 0) <= now)
        return True

    def update_social_delivery(self, subscription_id: int, event_key: str, message_id: int, state: str = "sent") -> None:
        with self._connection() as connection:
            connection.execute("UPDATE social_deliveries SET discord_message_id=?,state=?,updated_at=? WHERE subscription_id=? AND event_key=?", (message_id, state, int(time.time()), subscription_id, event_key))

    def fail_social_delivery(self, subscription_id: int, event_key: str, error: str, *, retry: bool) -> None:
        now = int(time.time())
        with self._connection() as connection:
            row = connection.execute("SELECT attempts FROM social_deliveries WHERE subscription_id=? AND event_key=?", (subscription_id, event_key)).fetchone()
            attempts = int(row["attempts"] if row else 0) + 1
            delay = min(3600, 15 * (2 ** min(attempts, 8))) if retry else 0
            connection.execute("""UPDATE social_deliveries SET state=?,attempts=?,next_attempt_at=?,last_error=?,updated_at=?
                WHERE subscription_id=? AND event_key=?""", ("retry" if retry else "failed", attempts, now + delay, error[:500], now, subscription_id, event_key))

    def purge_social_history(self, *, retention_days: int = 30) -> int:
        cutoff = int(time.time()) - max(1, retention_days) * 86400
        with self._connection() as connection:
            delivery_count = connection.execute("DELETE FROM social_deliveries WHERE updated_at<? AND state IN ('sent','failed')", (cutoff,)).rowcount
            event_count = connection.execute("DELETE FROM social_events WHERE processed_at IS NOT NULL AND processed_at<?", (cutoff,)).rowcount
        return int(delivery_count + event_count)

    def set_social_live_message(self, subscription_id: int, provider: str, account_id: str, channel_id: int, message_id: int) -> None:
        with self._connection() as connection:
            connection.execute("INSERT INTO social_live_messages(subscription_id,provider,account_id,discord_channel_id,discord_message_id) VALUES(?,?,?,?,?) ON CONFLICT(subscription_id,provider,account_id) DO UPDATE SET discord_channel_id=excluded.discord_channel_id,discord_message_id=excluded.discord_message_id", (subscription_id, provider, account_id, channel_id, message_id))

    def social_live_message(self, subscription_id: int, provider: str, account_id: str) -> dict[str, int] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT discord_channel_id,discord_message_id FROM social_live_messages WHERE subscription_id=? AND provider=? AND account_id=?", (subscription_id, provider, account_id)).fetchone()
        return dict(row) if row else None

    def clear_social_live_message(self, subscription_id: int, provider: str, account_id: str) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM social_live_messages WHERE subscription_id=? AND provider=? AND account_id=?", (subscription_id, provider, account_id))

    def enabled_module_guild_ids(self, module_id: str) -> list[int]:
        with self._connection() as connection:
            rows = connection.execute("SELECT guild_id FROM guild_modules WHERE module_id=? AND enabled=1", (module_id,)).fetchall()
        return [row["guild_id"] for row in rows]

    def add_case(self, guild_id: int, user_id: int, action: str, reason: str | None, moderator_id: int | None = None,
                 expires_at: int | None = None, dm_sent: bool = False, *, moderation_event_id: int | None = None,
                 moderation_rule_id: int | None = None, source: str = "manual", points: int = 0) -> int:
        weights = {"warn": -10, "timeout": -20, "kick": -30, "ban": -40, "spam": -15, "anti_spam": -15, "chat_filter": -10, "phishing": -20}
        now = int(time.time())
        with self._connection() as c:
            cursor = c.execute("""INSERT INTO moderation_cases
                (guild_id,user_id,moderator_id,action,reason,expires_at,dm_sent,created_at,moderation_event_id,moderation_rule_id,source,points)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (guild_id,user_id,moderator_id,action,reason,expires_at,int(dm_sent),now,moderation_event_id,moderation_rule_id,source,points))
            trust_enabled = c.execute("SELECT enabled FROM guild_modules WHERE guild_id=? AND module_id='trust_score'", (guild_id,)).fetchone()
            if action in weights and trust_enabled and trust_enabled["enabled"]:
                c.execute("INSERT INTO trust_events (guild_id,user_id,category,weight,reason,created_at) VALUES (?,?,?,?,?,?)", (guild_id, user_id, action, weights[action], reason, now))
        return int(cursor.lastrowid)

    def trust_score(self, guild_id: int, user_id: int, retention_days: int = 90) -> dict[str, Any]:
        cutoff = int(time.time()) - max(1, retention_days) * 86400
        with self._connection() as c:
            rows = c.execute("SELECT category,weight,reason,created_at FROM trust_events WHERE guild_id=? AND user_id=? AND created_at>=? ORDER BY created_at DESC", (guild_id, user_id, cutoff)).fetchall()
        events = [dict(row) for row in rows]
        return {"score": max(0, min(100, 100 + sum(event["weight"] for event in events))), "events": events}

    def clear_trust_events(self, guild_id: int, user_id: int) -> None:
        with self._connection() as c:
            c.execute("DELETE FROM trust_events WHERE guild_id=? AND user_id=?", (guild_id, user_id))

    def purge_trust_events(self, guild_id: int, retention_days: int) -> int:
        cutoff = int(time.time()) - max(1, retention_days) * 86400
        with self._connection() as c:
            cursor = c.execute("DELETE FROM trust_events WHERE guild_id=? AND created_at<?", (guild_id, cutoff))
        return cursor.rowcount

    def recent_cases(self, guild_id: int, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        with self._connection() as c:
            rows = c.execute("SELECT * FROM moderation_cases WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT ?", (guild_id, user_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def cached_url_result(self, url_hash: str) -> bool | None:
        with self._connection() as c: row=c.execute("SELECT unsafe FROM safe_browsing_cache WHERE url_hash=? AND expires_at>?",(url_hash,int(time.time()))).fetchone()
        return bool(row["unsafe"]) if row else None

    def cache_url_result(self, url_hash: str, unsafe: bool, ttl: int = 3600) -> None:
        with self._connection() as c: c.execute("INSERT OR REPLACE INTO safe_browsing_cache VALUES (?,?,?)",(url_hash,int(unsafe),int(time.time())+ttl))


    def add_temporary_voice_channel(self, channel_id: int, guild_id: int, owner_id: int) -> None:
        with self._connection() as c:
            c.execute("INSERT OR REPLACE INTO temporary_voice_channels (channel_id,guild_id,owner_id,created_at) VALUES (?,?,?,?)", (channel_id, guild_id, owner_id, int(time.time())))

    def temporary_voice_channel(self, channel_id: int) -> dict[str, int] | None:
        with self._connection() as c:
            row = c.execute("SELECT guild_id,owner_id FROM temporary_voice_channels WHERE channel_id=?", (channel_id,)).fetchone()
        return {"guild_id": row["guild_id"], "owner_id": row["owner_id"]} if row else None

    def remove_temporary_voice_channel(self, channel_id: int) -> None:
        with self._connection() as c:
            c.execute("DELETE FROM temporary_voice_channels WHERE channel_id=?", (channel_id,))


    def create_poll(self, message_id: int, guild_id: int, channel_id: int, creator_id: int, question: str, options: list[str], image_url: str | None, closes_at: int | None) -> None:
        if not 2 <= len(options) <= 10:
            raise ValueError("Polls require 2 to 10 options")
        with self._connection() as c:
            c.execute("INSERT INTO polls (message_id,guild_id,channel_id,creator_id,question,options_json,image_url,closes_at,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (message_id, guild_id, channel_id, creator_id, question, json.dumps(options, ensure_ascii=False), image_url, closes_at, int(time.time())))

    def poll(self, message_id: int) -> dict[str, Any] | None:
        with self._connection() as c:
            row = c.execute("SELECT * FROM polls WHERE message_id=?", (message_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["options"] = json.loads(data.pop("options_json"))
        return data

    def cast_poll_vote(self, message_id: int, user_id: int, option_index: int) -> list[int] | None:
        with self._connection() as c:
            poll = c.execute("SELECT options_json,closes_at,status FROM polls WHERE message_id=?", (message_id,)).fetchone()
            if not poll or poll["status"] != "open" or (poll["closes_at"] and poll["closes_at"] <= int(time.time())):
                return None
            if not 0 <= option_index < len(json.loads(poll["options_json"])):
                return None
            c.execute("INSERT INTO poll_votes (message_id,user_id,option_index,created_at) VALUES (?,?,?,?) ON CONFLICT(message_id,user_id) DO UPDATE SET option_index=excluded.option_index,created_at=excluded.created_at", (message_id, user_id, option_index, int(time.time())))
            rows = c.execute("SELECT option_index,COUNT(*) AS votes FROM poll_votes WHERE message_id=? GROUP BY option_index", (message_id,)).fetchall()
        counts = [0] * len(json.loads(poll["options_json"]))
        for row in rows:
            counts[row["option_index"]] = row["votes"]
        return counts

    def close_expired_polls(self) -> list[dict[str, Any]]:
        now = int(time.time())
        with self._connection() as c:
            rows = c.execute("SELECT * FROM polls WHERE status='open' AND closes_at IS NOT NULL AND closes_at<=?", (now,)).fetchall()
            c.execute("UPDATE polls SET status='closed' WHERE status='open' AND closes_at IS NOT NULL AND closes_at<=?", (now,))
        return [dict(row) for row in rows]

    # Text and voice leveling statistics.
    def get_user(self, guild_id: int, user_id: int) -> dict[str, int]:
        with self._connection() as connection:
            row = connection.execute("SELECT xp FROM guild_users WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)).fetchone()
        return {"xp": row["xp"]} if row else {"xp": 0}

    def add_xp(self, guild_id: int, user_id: int, amount: int) -> dict[str, int]:
        with self._connection() as connection:
            connection.execute("INSERT INTO guild_users (guild_id, user_id, xp) VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET xp = xp + excluded.xp", (guild_id, user_id, amount))
        return self.get_user(guild_id, user_id)

    def get_voice_user(self, guild_id: int, user_id: int) -> dict[str, int]:
        with self._connection() as connection:
            row = connection.execute("SELECT xp FROM guild_voice_users WHERE guild_id=? AND user_id=?", (guild_id, user_id)).fetchone()
        return {"xp": row["xp"]} if row else {"xp": 0}

    def add_voice_xp(self, guild_id: int, user_id: int, amount: int) -> dict[str, int]:
        with self._connection() as connection:
            connection.execute("INSERT INTO guild_voice_users (guild_id,user_id,xp) VALUES (?,?,?) ON CONFLICT(guild_id,user_id) DO UPDATE SET xp=xp+excluded.xp", (guild_id, user_id, amount))
        return self.get_voice_user(guild_id, user_id)

    def voice_leaderboard(self, guild_id: int, limit: int = 5) -> list[dict[str, int]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT user_id,xp FROM guild_voice_users WHERE guild_id=? ORDER BY xp DESC,user_id ASC LIMIT ?", (guild_id, limit)).fetchall()
        return [{"user_id": row["user_id"], "xp": row["xp"]} for row in rows]


    def leaderboard(self, guild_id: int, limit: int = 5) -> list[dict[str, int]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT user_id, xp FROM guild_users WHERE guild_id = ? ORDER BY xp DESC, user_id ASC LIMIT ?", (guild_id, limit)).fetchall()
        return [{"user_id": row["user_id"], "xp": row["xp"]} for row in rows]
