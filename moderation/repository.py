"""Moderation persistence; schema is managed by the migration CLI."""
import json
import time
from typing import Any

from jobs import QueueRepository, QueueSpec
from jobs.catalog import QUEUE_SPECS
from database import lock_resource, require_current, transaction
from guild_settings.moderation.moderation import normalize as moderation_settings


class ModerationRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        require_current(self.database_url)
        self.request_jobs = QueueRepository(self.database_url, QUEUE_SPECS['moderation_action_requests'])
        self.schedule_jobs = QueueRepository(self.database_url, QUEUE_SPECS['scheduled_moderation_actions'])

    def _connection(self):
        return transaction(self.database_url)

    @staticmethod
    def _moderation_rule(row: dict[str, Any]) -> dict[str, Any]:
        value = dict(row)
        for column, key in (("trigger_config_json", "trigger_config"), ("conditions_json", "conditions"), ("exemptions_json", "exemptions"), ("actions_json", "actions")):
            value[key] = json.loads(value.pop(column))
        value["enabled"] = bool(value["enabled"])
        value["stop_on_match"] = bool(value["stop_on_match"])
        return value

    def moderation_rules(self, guild_id: int, *, family: str | None = None, enabled_only: bool = False) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM moderation_rules WHERE guild_id=%s", [guild_id]
        if family:
            query, params = query + " AND family=%s", [guild_id, family]
        if enabled_only:
            query += " AND enabled=1"
        query += " ORDER BY priority,id"
        with self._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._moderation_rule(row) for row in rows]

    def moderation_rule(self, guild_id: int, rule_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM moderation_rules WHERE guild_id=%s AND id=%s", (guild_id, rule_id)).fetchone()
        return self._moderation_rule(row) if row else None

    def next_moderation_rule_priority(self, guild_id: int, family: str) -> int:
        with self._connection() as connection:
            row = connection.execute("SELECT COALESCE(MAX(priority),0) AS value FROM moderation_rules WHERE guild_id=%s AND family=%s", (guild_id, family)).fetchone()
        return min(10000, int(row["value"]) + 10)

    def reorder_moderation_rules(self, guild_id: int, family: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not items or len(items) > 200:
            raise ValueError("Rule order must contain 1 to 200 rules")
        ids = [int(item.get("id", 0)) for item in items]
        if any(value <= 0 for value in ids) or len(ids) != len(set(ids)):
            raise ValueError("Rule order contains invalid or duplicate IDs")
        now = int(time.time())
        with self._connection() as connection:
            lock_resource(connection, "guild-module", f"{guild_id}:moderation")
            rows = connection.execute(f"SELECT id,revision FROM moderation_rules WHERE guild_id=%s AND family=%s AND id IN ({','.join('%s' for _ in ids)})", (guild_id, family, *ids)).fetchall()
            current = {int(row["id"]): int(row["revision"]) for row in rows}
            if set(current) != set(ids):
                raise ValueError("Rule order contains a rule from another server or family")
            for position, item in enumerate(items, 1):
                rule_id = int(item["id"])
                if item.get("revision") is not None and int(item["revision"]) != current[rule_id]:
                    raise RuntimeError("revision_conflict")
                connection.execute("UPDATE moderation_rules SET priority=%s,stop_on_match=%s,revision=revision+1,updated_at=%s WHERE guild_id=%s AND family=%s AND id=%s",
                    (position * 10, int(bool(item.get("stop_on_match"))), now, guild_id, family, rule_id))
            core = connection.execute("SELECT enabled,settings_json FROM guild_modules WHERE guild_id=%s AND module_id='moderation'", (guild_id,)).fetchone()
            settings = moderation_settings(json.loads(core["settings_json"]) if core else {})
            settings["rules_revision"] = int(settings.get("rules_revision", 0)) + 1
            connection.execute("""INSERT INTO guild_modules(guild_id,module_id,enabled,settings_json) VALUES(%s,'moderation',%s,%s)
                ON CONFLICT(guild_id,module_id) DO UPDATE SET settings_json=excluded.settings_json""",
                (guild_id, int(core["enabled"]) if core else 0, json.dumps(settings)))
        return self.moderation_rules(guild_id, family=family)

    def save_moderation_rule(self, guild_id: int, rule: dict[str, Any], rule_id: int | None = None, *, expected_revision: int | None = None) -> dict[str, Any]:
        now = int(time.time())
        values = (rule["family"], rule["event_type"], str(rule["name"])[:100], int(bool(rule.get("enabled", True))),
            rule.get("mode", "enforce"), int(rule.get("priority", 100)), int(bool(rule.get("stop_on_match"))), rule["trigger_type"],
            json.dumps(rule.get("trigger_config", {}), ensure_ascii=False), json.dumps(rule.get("conditions", {})),
            json.dumps(rule.get("exemptions", {})), json.dumps(rule.get("actions", []), ensure_ascii=False))
        with self._connection() as connection:
            lock_resource(connection, "guild-module", f"{guild_id}:moderation")
            if rule_id is None:
                count = connection.execute("SELECT COUNT(*) AS count FROM moderation_rules WHERE guild_id=%s", (guild_id,)).fetchone()["count"]
                if count >= 200:
                    raise ValueError("A server can have at most 200 Moderation rules")
                cursor = connection.execute('INSERT INTO moderation_rules\n                    (guild_id,family,event_type,name,enabled,mode,priority,stop_on_match,trigger_type,trigger_config_json,conditions_json,exemptions_json,actions_json,created_at,updated_at)\n                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id', (guild_id, *values, now, now))
                inserted = cursor.fetchone()
                rule_id = int(inserted["id"])
            else:
                current = connection.execute('SELECT revision FROM moderation_rules WHERE guild_id=%s AND id=%s FOR UPDATE', (guild_id, rule_id)).fetchone()
                if current is None:
                    raise ValueError('Moderation rule not found')
                if expected_revision is not None and current['revision'] != expected_revision:
                    raise RuntimeError('revision_conflict')
                cursor = connection.execute("""UPDATE moderation_rules SET family=%s,event_type=%s,name=%s,enabled=%s,mode=%s,priority=%s,stop_on_match=%s,trigger_type=%s,
                    trigger_config_json=%s,conditions_json=%s,exemptions_json=%s,actions_json=%s,revision=revision+1,updated_at=%s WHERE guild_id=%s AND id=%s""",
                    (*values, now, guild_id, rule_id))
                if cursor.rowcount != 1:
                    raise ValueError("Moderation rule not found")
            row = connection.execute("SELECT * FROM moderation_rules WHERE guild_id=%s AND id=%s", (guild_id, rule_id)).fetchone()
            core = connection.execute("SELECT enabled,settings_json FROM guild_modules WHERE guild_id=%s AND module_id='moderation'", (guild_id,)).fetchone()
            settings = moderation_settings(json.loads(core["settings_json"]) if core else {})
            settings["rules_revision"] = int(settings.get("rules_revision", 0)) + 1
            connection.execute("""INSERT INTO guild_modules(guild_id,module_id,enabled,settings_json) VALUES(%s,'moderation',%s,%s)
                ON CONFLICT(guild_id,module_id) DO UPDATE SET settings_json=excluded.settings_json""",
                (guild_id, int(core["enabled"]) if core else 0, json.dumps(settings)))
        return self._moderation_rule(row)

    def delete_moderation_rule(self, guild_id: int, rule_id: int, *, expected_revision: int | None = None) -> bool:
        with self._connection() as connection:
            lock_resource(connection, "guild-module", f"{guild_id}:moderation")
            current = connection.execute('SELECT revision FROM moderation_rules WHERE guild_id=%s AND id=%s FOR UPDATE', (guild_id, rule_id)).fetchone()
            if expected_revision is not None and (current is None or current['revision'] != expected_revision):
                raise RuntimeError('revision_conflict')
            cursor = connection.execute("DELETE FROM moderation_rules WHERE guild_id=%s AND id=%s", (guild_id, rule_id))
            if cursor.rowcount:
                row = connection.execute("SELECT settings_json FROM guild_modules WHERE guild_id=%s AND module_id='moderation'", (guild_id,)).fetchone()
                settings = moderation_settings(json.loads(row["settings_json"]) if row else {})
                settings["rules_revision"] = int(settings.get("rules_revision", 0)) + 1
                connection.execute("UPDATE guild_modules SET settings_json=%s WHERE guild_id=%s AND module_id='moderation'", (json.dumps(settings), guild_id))
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
            cursor = connection.execute('INSERT INTO moderation_events\n                (guild_id,rule_id,family,event_type,source,actor_id,actor_kind,target_user_id,channel_id,target_id,reason,evidence_text,evidence_json,mode,created_at,evidence_expires_at,dedupe_key)\n                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id', (guild_id,rule_id,family,event_type,source,actor_id,actor_kind,target_user_id,
                channel_id,target_id,reason,evidence_text[:1000] if evidence_text else None,json.dumps(evidence or {},ensure_ascii=False),mode,now,expires,dedupe_key))
            inserted = cursor.fetchone()
        return int(inserted["id"]) if inserted else None

    def finish_moderation_event(self, event_id: int, results: list[dict[str, Any]]) -> None:
        now = int(time.time())
        with self._connection() as connection:
            for sequence, result in enumerate(results):
                detail = {key: value for key, value in result.items() if key not in {"type", "status", "case_id"}}
                connection.execute('INSERT INTO moderation_action_results\n                    (event_id,sequence,action_type,status,case_id,detail_json,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(event_id,sequence) DO UPDATE SET action_type=excluded.action_type,status=excluded.status,case_id=excluded.case_id,detail_json=excluded.detail_json,created_at=excluded.created_at',
                    (event_id,sequence,str(result.get("type","unknown")),str(result.get("status","unknown")),result.get("case_id"),json.dumps(detail,ensure_ascii=False),now))
            case_id = next((int(item["case_id"]) for item in results if item.get("case_id")), None)
            if case_id:
                connection.execute("UPDATE moderation_events SET case_id=%s WHERE id=%s", (case_id,event_id))

    def case_execution(self, guild_id: int, key: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM moderation_events WHERE guild_id=%s AND dedupe_key=%s AND source='case_execution' FOR UPDATE", (guild_id, key)).fetchone()
        return dict(row) if row else None

    def recent_moderation_events(self, guild_id: int, *, family: str | None = None, user_id: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM moderation_events WHERE guild_id=%s", [guild_id]
        if family:
            query, params = query + " AND family=%s", [*params, family]
        if user_id:
            query, params = query + " AND target_user_id=%s", [*params, user_id]
        query += " ORDER BY id DESC LIMIT %s"
        params.append(max(1, min(limit, 200)))
        with self._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [{**dict(row), "evidence": json.loads(row["evidence_json"])} for row in rows]

    def moderation_summary(self, guild_id: int) -> dict[str, Any]:
        now = int(time.time())
        with self._connection() as connection:
            rules = {row["family"]: row["count"] for row in connection.execute("SELECT family,COUNT(*) count FROM moderation_rules WHERE guild_id=%s AND enabled=1 GROUP BY family", (guild_id,)).fetchall()}
            events = connection.execute("SELECT COUNT(*) count FROM moderation_events WHERE guild_id=%s AND created_at>%s", (guild_id, now - 86400)).fetchone()["count"]
            lockdowns = connection.execute("SELECT COUNT(*) count FROM moderation_lockdowns WHERE guild_id=%s AND status='active'", (guild_id,)).fetchone()["count"]
            sanctioned = connection.execute("SELECT COUNT(DISTINCT user_id) count FROM moderation_points WHERE guild_id=%s AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>%s)", (guild_id,now)).fetchone()["count"]
        return {"rules": rules, "events_24h": int(events), "active_lockdowns": int(lockdowns), "sanctioned_users": int(sanctioned)}

    def start_lockdown(self, guild_id: int, *, reason: str | None, started_by: int | None,
            unlock_at: int | None, source_event_id: int | None = None, lease=None) -> int:
        with self._connection() as connection:
            if lease:
                lease.guard(connection)
            lock_resource(connection, "moderation-lockdown", guild_id)
            existing = connection.execute("SELECT id FROM moderation_lockdowns WHERE guild_id=%s AND status='active'", (guild_id,)).fetchone()
            if existing:
                return int(existing["id"])
            cursor = connection.execute('INSERT INTO moderation_lockdowns\n                (guild_id,source_event_id,reason,started_by,started_at,unlock_at) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id',
                (guild_id,source_event_id,reason,started_by,int(time.time()),unlock_at))
            inserted = cursor.fetchone()
        return int(inserted["id"])

    def save_lockdown_snapshot(self, lockdown_id: int, channel_id: int, role_id: int, before: dict[str, Any], applied: dict[str, Any], *, lease=None) -> None:
        with self._connection() as connection:
            if lease:
                lease.guard(connection)
            connection.execute('INSERT INTO moderation_lockdown_snapshots\n                (lockdown_id,channel_id,role_id,before_json,applied_json) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                (lockdown_id,channel_id,role_id,json.dumps(before),json.dumps(applied)))

    def active_lockdown(self, guild_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM moderation_lockdowns WHERE guild_id=%s AND status='active' ORDER BY id DESC LIMIT 1", (guild_id,)).fetchone()
        return dict(row) if row else None

    def due_lockdowns(self, now: int | None = None) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM moderation_lockdowns WHERE status='active' AND unlock_at IS NOT NULL AND unlock_at<=%s", (int(time.time()) if now is None else now,)).fetchall()
        return [dict(row) for row in rows]

    def lockdown_snapshots(self, lockdown_id: int) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM moderation_lockdown_snapshots WHERE lockdown_id=%s ORDER BY channel_id", (lockdown_id,)).fetchall()
        return [{**dict(row), "before": json.loads(row["before_json"]), "applied": json.loads(row["applied_json"])} for row in rows]

    def finish_lockdown(self, lockdown_id: int, *, error: str | None = None, lease=None) -> None:
        with self._connection() as connection:
            if lease:
                lease.guard(connection)
            if error:
                connection.execute("UPDATE moderation_lockdowns SET last_error=%s WHERE id=%s AND status='active'", (error[:500], lockdown_id))
            else:
                connection.execute("UPDATE moderation_lockdowns SET status='completed',completed_at=%s,last_error=NULL WHERE id=%s AND status='active'", (int(time.time()), lockdown_id))
                connection.execute('UPDATE moderation_raid_state SET active=0 WHERE lockdown_id=%s', (lockdown_id,))

    def set_raid_state(self, guild_id: int, active: bool, *, source_rule_id: int | None = None, lockdown_id: int | None = None, lease=None) -> None:
        now = int(time.time())
        with self._connection() as connection:
            if lease:
                lease.guard(connection)
            connection.execute("""INSERT INTO moderation_raid_state(guild_id,active,started_at,last_signal_at,source_rule_id,lockdown_id)
                VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(guild_id) DO UPDATE SET active=excluded.active,
                started_at=CASE WHEN excluded.active=1 AND moderation_raid_state.active=0 THEN excluded.started_at ELSE moderation_raid_state.started_at END,
                last_signal_at=excluded.last_signal_at,source_rule_id=excluded.source_rule_id,lockdown_id=excluded.lockdown_id""",
                (guild_id,int(active),now if active else None,now,source_rule_id,lockdown_id))

    def stale_raid_states(self, quiet_before: int) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM moderation_raid_state WHERE active=1 AND last_signal_at<=%s ORDER BY last_signal_at",
                (quiet_before,),
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_stale_raid(self, guild_id: int, observed_signal: int) -> bool:
        with self._connection() as connection:
            changed = connection.execute("""UPDATE moderation_raid_state SET active=0
                WHERE guild_id=%s AND active=1 AND last_signal_at=%s
                AND NOT EXISTS(SELECT 1 FROM moderation_lockdowns WHERE guild_id=%s AND status='active')""",
                (guild_id, observed_signal, guild_id))
            return changed.rowcount == 1

    def enqueue_moderation_action(self, guild_id: int, moderator_id: int, action: str, *, target_user_id: int | None = None,
            channel_id: int | None = None, reason: str | None = None, options: dict[str, Any] | None = None, dedupe_key: str) -> int | None:
        with self._connection() as connection:
            cursor = connection.execute('INSERT INTO moderation_action_requests\n                (guild_id,moderator_id,target_user_id,channel_id,action,reason,options_json,created_at,dedupe_key)\n                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id', (guild_id,moderator_id,target_user_id,channel_id,action,reason,json.dumps(options or {}),int(time.time()),dedupe_key))
            inserted = cursor.fetchone()
        return int(inserted["id"]) if inserted else None

    def pending_moderation_actions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM moderation_action_requests WHERE status='pending' ORDER BY id LIMIT %s", (max(1,min(limit,100)),)).fetchall()
        return [{**dict(row), "options": json.loads(row["options_json"])} for row in rows]


    def active_points(self, guild_id: int, user_id: int, now: int | None = None) -> int:
        current = int(time.time()) if now is None else now
        with self._connection() as connection:
            row = connection.execute("""SELECT COALESCE(SUM(points),0) AS total FROM moderation_points
                WHERE guild_id=%s AND user_id=%s AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>%s)""", (guild_id,user_id,current)).fetchone()
        return int(row["total"])

    def add_points(self, guild_id: int, user_id: int, points: int, reason: str | None, *, moderation_rule_id: int | None = None,
                   moderation_event_id: int | None = None, expires_at: int | None = None) -> tuple[int, int, int]:
        if not 1 <= points <= 1000:
            raise ValueError("Points must be between 1 and 1000")
        now = int(time.time())
        with self._connection() as connection:
            lock_resource(connection, "moderation-points", f"{guild_id}:{user_id}")
            before = connection.execute("""SELECT COALESCE(SUM(points),0) AS total FROM moderation_points
                WHERE guild_id=%s AND user_id=%s AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>%s)""", (guild_id,user_id,now)).fetchone()["total"]
            cursor = connection.execute('INSERT INTO moderation_points\n                (guild_id,user_id,points,reason,moderation_rule_id,moderation_event_id,created_at,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',
                (guild_id,user_id,points,reason,moderation_rule_id,moderation_event_id,now,expires_at))
            inserted = cursor.fetchone()
        return int(inserted["id"]), int(before), int(before) + points

    def revoke_points(self, guild_id: int, user_id: int) -> int:
        with self._connection() as connection:
            lock_resource(connection, "moderation-points", f"{guild_id}:{user_id}")
            cursor = connection.execute("UPDATE moderation_points SET revoked_at=%s WHERE guild_id=%s AND user_id=%s AND revoked_at IS NULL", (int(time.time()),guild_id,user_id))
        return cursor.rowcount

    def clear_warnings(self, guild_id: int, user_id: int) -> int:
        with self._connection() as connection:
            lock_resource(connection, "moderation-points", f"{guild_id}:{user_id}")
            cursor = connection.execute("UPDATE moderation_points SET revoked_at=%s WHERE guild_id=%s AND user_id=%s AND revoked_at IS NULL", (int(time.time()),guild_id,user_id))
        return cursor.rowcount

    def schedule_moderation_action(self, guild_id: int, user_id: int, action: str, due_at: int, reason: str | None, case_id: int | None) -> int:
        with self._connection() as connection:
            cursor = connection.execute('INSERT INTO scheduled_moderation_actions(guild_id,user_id,action,due_at,reason,case_id) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id', (guild_id,user_id,action,due_at,reason,case_id))
            inserted = cursor.fetchone()
        return int(inserted["id"])

    def due_moderation_actions(self, now: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
        current = int(time.time()) if now is None else now
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM scheduled_moderation_actions WHERE completed_at IS NULL AND due_at<=%s ORDER BY due_at LIMIT %s", (current,max(1,min(limit,500)))).fetchall()
        return [dict(row) for row in rows]


    def purge_moderation_evidence(self, now: int | None = None) -> int:
        with self._connection() as connection:
            cursor = connection.execute("UPDATE moderation_events SET evidence_text=NULL,evidence_json='{}',evidence_expires_at=NULL WHERE evidence_expires_at IS NOT NULL AND evidence_expires_at<=%s AND NOT(source='case_execution' AND case_id IS NULL)", (int(time.time()) if now is None else now,))
        return cursor.rowcount

    def add_case(self, guild_id: int, user_id: int, action: str, reason: str | None, moderator_id: int | None = None,
                 expires_at: int | None = None, dm_sent: bool = False, *, moderation_event_id: int | None = None,
                 moderation_rule_id: int | None = None, source: str = "manual", points: int = 0,
                 execution_event_id: int | None = None) -> int:
        weights = {"warn": -10, "timeout": -20, "kick": -30, "ban": -40, "spam": -15, "anti_spam": -15, "chat_filter": -10, "phishing": -20}
        now = int(time.time())
        with self._connection() as c:
            if execution_event_id is not None:
                receipt = c.execute("SELECT case_id FROM moderation_events WHERE id=%s AND guild_id=%s AND source='case_execution' FOR UPDATE", (execution_event_id, guild_id)).fetchone()
                if receipt is None:
                    raise ValueError('Execution intent not found')
                if receipt['case_id'] is not None:
                    return int(receipt['case_id'])
            cursor = c.execute('INSERT INTO moderation_cases\n                (guild_id,user_id,moderator_id,action,reason,expires_at,dm_sent,created_at,moderation_event_id,moderation_rule_id,source,points)\n                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id', (guild_id,user_id,moderator_id,action,reason,expires_at,int(dm_sent),now,moderation_event_id,moderation_rule_id,source,points))
            inserted = cursor.fetchone()
            trust_enabled = c.execute("SELECT enabled FROM guild_modules WHERE guild_id=%s AND module_id='trust_score'", (guild_id,)).fetchone()
            if action in weights and trust_enabled and trust_enabled["enabled"]:
                c.execute("INSERT INTO trust_events (guild_id,user_id,category,weight,reason,created_at) VALUES (%s,%s,%s,%s,%s,%s)", (guild_id, user_id, action, weights[action], reason, now))
            if execution_event_id is not None:
                c.execute('UPDATE moderation_events SET case_id=%s WHERE id=%s', (inserted["id"], execution_event_id))
                if action == 'tempban' and expires_at is not None:
                    c.execute("INSERT INTO scheduled_moderation_actions(guild_id,user_id,action,due_at,reason,case_id) VALUES(%s,%s,'unban',%s,%s,%s)", (guild_id, user_id, expires_at, reason, inserted["id"]))
        return int(inserted["id"])

    def trust_score(self, guild_id: int, user_id: int, retention_days: int = 90) -> dict[str, Any]:
        cutoff = int(time.time()) - max(1, retention_days) * 86400
        with self._connection() as c:
            rows = c.execute("SELECT category,weight,reason,created_at FROM trust_events WHERE guild_id=%s AND user_id=%s AND created_at>=%s ORDER BY created_at DESC", (guild_id, user_id, cutoff)).fetchall()
        events = [dict(row) for row in rows]
        return {"score": max(0, min(100, 100 + sum(event["weight"] for event in events))), "events": events}

    def clear_trust_events(self, guild_id: int, user_id: int) -> None:
        with self._connection() as c:
            c.execute("DELETE FROM trust_events WHERE guild_id=%s AND user_id=%s", (guild_id, user_id))

    def purge_trust_events(self, guild_id: int, retention_days: int) -> int:
        cutoff = int(time.time()) - max(1, retention_days) * 86400
        with self._connection() as c:
            cursor = c.execute("DELETE FROM trust_events WHERE guild_id=%s AND created_at<%s", (guild_id, cutoff))
        return cursor.rowcount

    def recent_cases(self, guild_id: int, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        with self._connection() as c:
            rows = c.execute("SELECT * FROM moderation_cases WHERE guild_id=%s AND user_id=%s ORDER BY id DESC LIMIT %s", (guild_id, user_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def cached_url_result(self, url_hash: str) -> bool | None:
        with self._connection() as c: row=c.execute("SELECT unsafe FROM safe_browsing_cache WHERE url_hash=%s AND expires_at>%s",(url_hash,int(time.time()))).fetchone()
        return bool(row["unsafe"]) if row else None

    def cache_url_result(self, url_hash: str, unsafe: bool, ttl: int = 3600) -> None:
        with self._connection() as c: c.execute('INSERT INTO safe_browsing_cache VALUES (%s,%s,%s) ON CONFLICT(url_hash) DO UPDATE SET unsafe=excluded.unsafe,expires_at=excluded.expires_at',(url_hash,int(unsafe),int(time.time())+ttl))
