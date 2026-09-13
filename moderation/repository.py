"""Moderation persistence; schema is managed by the migration CLI."""
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from database import require_current, transaction
from guild_settings.models import moderation_settings


class ModerationRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        require_current(self.database_path)

    def _connection(self):
        return transaction(self.database_path)

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
            settings = moderation_settings(json.loads(core["settings_json"]) if core else {})
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
            settings = moderation_settings(json.loads(core["settings_json"]) if core else {})
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
                settings = moderation_settings(json.loads(row["settings_json"]) if row else {})
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
