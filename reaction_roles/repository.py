"""PostgreSQL repository for Reaction Roles."""
from __future__ import annotations

import json
from contextlib import nullcontext
import time
from jobs import QueueRepository, QueueSpec, LostLease
from jobs.catalog import QUEUE_SPECS
from database import Connection, lock_resource, require_current, transaction
from typing import Any
from .models import ReactionRoleValidationError


class ReactionRoleOutbox(QueueRepository):
    def _claim_scope(self):
        return (" AND (action NOT IN ('reconcile_remove','reconcile_add','reconcile_selection') OR EXISTS (SELECT 1 FROM reaction_role_settings s WHERE s.guild_id=reaction_role_outbox.guild_id AND s.enabled=1))", ())

    def finish(self, claim, outcome):
        if claim.payload.get('action') not in {'reconcile_remove', 'reconcile_add', 'reconcile_selection'} or outcome.error != 'reaction_roles_disabled':
            return super().finish(claim, outcome)
        with transaction(self.database_url) as c:
            if self._owned_at(c, claim) is None:
                return False
            state = claim.payload['state']
            if state == 'processing':
                state = 'pending'
            return c.execute("""UPDATE reaction_role_outbox SET state=%s,attempts=%s,
                lease_owner=NULL,lease_token=NULL,lease_until=NULL WHERE id=%s""",
                (state, claim.attempt - 1, claim.id)).rowcount == 1


class ReactionRoleRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        require_current(self.database_url)
        self.outbox_jobs = ReactionRoleOutbox(self.database_url, QUEUE_SPECS['reaction_role_outbox'])
        self.schedule_jobs = QueueRepository(self.database_url, QUEUE_SPECS['reaction_role_schedules'])

    def connection(self):
        return transaction(self.database_url)

    def _guard_job(self, c, item, *, schedule=False):
        if not item or not item.get('_lease'):
            return
        queue = self.schedule_jobs if schedule else self.outbox_jobs
        row = c.execute(f'SELECT state,lease_owner,lease_token,lease_until FROM {queue.spec.table} WHERE id=%s FOR UPDATE', (item['id'],)).fetchone()
        identity = item['_lease']
        if (row is None or row['state'] != 'processing' or row['lease_owner'] != identity['owner']
                or row['lease_token'] != identity['token'] or row['lease_until'] is None
                or row['lease_until'] <= int(queue.clock())):
            raise LostLease('Reaction Role queue ownership expired')

    def guard_delivery(self, item, *, schedule=False):
        with self.connection() as c:
            self._guard_job(c, item, schedule=schedule)

    @staticmethod
    def _detach_expiries(c, config_id, mapping_ids=None):
        suffix = '' if mapping_ids is None else f" AND a.mapping_id IN ({','.join('%s' for _ in mapping_ids)})"
        values = (config_id,) if mapping_ids is None else (config_id, *mapping_ids)
        c.execute(f"""UPDATE reaction_role_schedules s SET role_id=a.role_id,mapping_id=NULL
            FROM reaction_role_assignments a WHERE a.message_config_id=%s AND s.message_config_id=a.message_config_id
            AND s.mapping_id=a.mapping_id AND s.user_id=a.user_id AND s.scheduled_for=a.expires_at
            AND s.selection_generation=a.generation AND s.kind='temp_role' AND a.state='active'
            AND s.state IN ('pending','retry','processing'){suffix}""", values)

    def settings(self, guild_id: int) -> dict[str, Any]:
        with self.connection() as c:
            lock_resource(c, "reaction-role-settings", guild_id)
            row = c.execute("SELECT * FROM reaction_role_settings WHERE guild_id=%s", (guild_id,)).fetchone()
            if not row:
                has_active_message = c.execute(
                    "SELECT 1 FROM reaction_role_messages_v2 WHERE guild_id=%s AND enabled=1 LIMIT 1", (guild_id,)
                ).fetchone()
                if has_active_message:
                    # Early V2 builds could publish a panel without creating its
                    # guild settings row. Treat an existing active panel as the
                    # intended enable signal, while preserving an explicit saved
                    # disabled setting once a row exists.
                    now = int(time.time())
                    c.execute(
                        "INSERT INTO reaction_role_settings(guild_id,enabled,updated_at) VALUES(%s,%s,%s)",
                        (guild_id, 1, now),
                    )
                    row = c.execute("SELECT * FROM reaction_role_settings WHERE guild_id=%s", (guild_id,)).fetchone()
        return dict(row) if row else {"guild_id": guild_id, "enabled": False, "log_channel_id": None, "denial_dm": True, "denial_dm_cooldown_seconds": 300, "audit_retention_days": 90, "revision": 0}

    def save_settings(self, guild_id: int, value: dict[str, Any], expected_revision: int | None) -> dict[str, Any]:
        now = int(time.time())
        with self.connection() as c:
            lock_resource(c, "reaction-role-settings", guild_id)
            row = c.execute("SELECT revision FROM reaction_role_settings WHERE guild_id=%s", (guild_id,)).fetchone()
            revision = int(row["revision"]) if row else 0
            if expected_revision is not None and revision != expected_revision:
                raise RuntimeError("revision_conflict")
            c.execute("""INSERT INTO reaction_role_settings(guild_id,enabled,log_channel_id,denial_dm,denial_dm_cooldown_seconds,audit_retention_days,revision,updated_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(guild_id) DO UPDATE SET enabled=excluded.enabled,log_channel_id=excluded.log_channel_id,
                denial_dm=excluded.denial_dm,denial_dm_cooldown_seconds=excluded.denial_dm_cooldown_seconds,
                audit_retention_days=excluded.audit_retention_days,revision=excluded.revision,updated_at=excluded.updated_at""",
                (guild_id, int(bool(value.get("enabled"))), value.get("log_channel_id"), int(bool(value.get("denial_dm", True))),
                 max(30, min(int(value.get("denial_dm_cooldown_seconds", 300)), 86400)), 90, revision + 1, now))
        return self.settings(guild_id)

    @staticmethod
    def _decode_message(row: dict[str, Any], mappings: list[dict[str, Any]], access: list[dict[str, Any]]) -> dict[str, Any]:
        value = dict(row)
        value.update({"locked": bool(value["locked"]), "enabled": bool(value["enabled"]), "embed": json.loads(value.pop("embed_json"))})
        value["mappings"] = [{"id": item["id"], "emoji": item["emoji_display"], "emoji_key": item["emoji_key"], "emoji_id": item["emoji_id"],
            "emoji_name": item["emoji_name"], "animated": bool(item["animated"]), "role_id": item["role_id"], "max_members": item["max_members"], "position": item["position"]} for item in mappings]
        value["whitelist_role_ids"] = [item["role_id"] for item in access if item["policy"] == "whitelist"]
        value["blacklist_role_ids"] = [item["role_id"] for item in access if item["policy"] == "blacklist"]
        if value["whitelist_role_ids"] and not value["blacklist_role_ids"]:
            value["access_policy"] = "whitelist"
        return value

    def message(self, guild_id: int, config_id: int, *, _conn=None) -> dict[str, Any] | None:
        with (nullcontext(_conn) if _conn is not None else self.connection()) as c:
            row = c.execute("SELECT * FROM reaction_role_messages_v2 WHERE guild_id=%s AND id=%s", (guild_id, config_id)).fetchone()
            if not row: return None
            mappings = c.execute("SELECT * FROM reaction_role_mappings_v2 WHERE message_config_id=%s ORDER BY position,id", (config_id,)).fetchall()
            access = c.execute("SELECT * FROM reaction_role_access_roles WHERE message_config_id=%s", (config_id,)).fetchall()
        return self._decode_message(row, mappings, access)

    def message_by_discord_id(self, guild_id: int, message_id: int) -> dict[str, Any] | None:
        with self.connection() as c:
            row = c.execute("SELECT id FROM reaction_role_messages_v2 WHERE guild_id=%s AND message_id=%s", (guild_id, message_id)).fetchone()
        return self.message(guild_id, int(row["id"])) if row else None

    def messages(self, guild_id: int, *, include_disabled: bool = True) -> list[dict[str, Any]]:
        query = "SELECT id FROM reaction_role_messages_v2 WHERE guild_id=%s" + ("" if include_disabled else " AND enabled=1") + " ORDER BY id DESC"
        with self.connection() as c: ids = [int(row["id"]) for row in c.execute(query, (guild_id,)).fetchall()]
        return [item for config_id in ids if (item := self.message(guild_id, config_id))]

    def _replace_children(self, c: Connection, config_id: int, value: dict[str, Any]) -> None:
        existing = {(row["emoji_key"], int(row["role_id"])): int(row["id"]) for row in c.execute(
            "SELECT id,emoji_key,role_id FROM reaction_role_mappings_v2 WHERE message_config_id=%s", (config_id,)).fetchall()}
        incoming = {(item["key"], int(item["role_id"])) for item in value["mappings"]}
        removed = [mapping_id for pair, mapping_id in existing.items() if pair not in incoming]
        if removed:
            # Mapping deletion cascades assignments. Preserve only the current
            # temporary expiry as a detached job before that evidence disappears.
            self._detach_expiries(c, config_id, removed)
            c.execute(f"DELETE FROM reaction_role_mappings_v2 WHERE id IN ({','.join('%s' for _ in removed)})", removed)
        for item in value["mappings"]:
            pair = (item["key"], int(item["role_id"]))
            if pair in existing:
                c.execute("UPDATE reaction_role_mappings_v2 SET emoji_display=%s,emoji_id=%s,emoji_name=%s,animated=%s,max_members=%s,position=%s WHERE id=%s",
                    (item["display"],item["emoji_id"],item["emoji_name"],int(item["animated"]),item["max_members"],item["position"],existing[pair]))
            else:
                c.execute("""INSERT INTO reaction_role_mappings_v2(message_config_id,emoji_key,emoji_display,emoji_id,emoji_name,animated,role_id,max_members,position)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (config_id,item["key"],item["display"],item["emoji_id"],item["emoji_name"],int(item["animated"]),item["role_id"],item["max_members"],item["position"]))
        c.execute("DELETE FROM reaction_role_access_roles WHERE message_config_id=%s", (config_id,))
        for policy, key in (("whitelist", "whitelist_role_ids"), ("blacklist", "blacklist_role_ids")):
            c.cursor().executemany("INSERT INTO reaction_role_access_roles(message_config_id,role_id,policy) VALUES(%s,%s,%s)", [(config_id, role_id, policy) for role_id in value[key]])

    @staticmethod
    def _check_link_group(c: Connection, guild_id: int, group_id: int | None) -> None:
        if group_id is not None and not c.execute(
            'SELECT id FROM reaction_role_link_groups WHERE guild_id=%s AND id=%s FOR SHARE',
            (guild_id, group_id),
        ).fetchone():
            raise ReactionRoleValidationError('link_group_invalid', 'このサーバーのLink Groupを選択してください。', 'link_group_id')

    def create_message(self, guild_id: int, value: dict[str, Any], actor_id: int | None = None, *, _conn=None) -> dict[str, Any]:
        now = int(time.time())
        with (nullcontext(_conn) if _conn is not None else self.connection()) as c:
            lock_resource(c, "reaction-role-settings", guild_id)
            self._check_link_group(c, guild_id, value.get('link_group_id'))
            # The first V2 configuration makes the feature usable immediately.
            # ON CONFLICT DO NOTHING means a deliberate administrator disable is
            # never overwritten by creating another configuration.
            c.execute(
                "INSERT INTO reaction_role_settings(guild_id,enabled,updated_at) VALUES(%s,1,%s) ON CONFLICT(guild_id) DO NOTHING",
                (guild_id, now),
            )
            cursor = c.execute('INSERT INTO reaction_role_messages_v2(guild_id,channel_id,message_id,name,source,behavior_type,locked,access_policy,selection_limit,temp_duration_seconds,self_destruct_at,embed_json,link_group_id,enabled,status,created_at,updated_at)\n                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id', (guild_id,value["channel_id"],value["message_id"],value["name"],value["source"],value["behavior_type"],int(value["locked"]),value["access_policy"],value["selection_limit"],value["temp_duration_seconds"],value["self_destruct_at"],json.dumps(value["embed"],ensure_ascii=False),value["link_group_id"],int(value["enabled"]),"active" if value["message_id"] else "pending",now,now)); inserted = cursor.fetchone()
            config_id = int(inserted["id"]); self._replace_children(c, config_id, value)
            if value["source"] == "bot": self._queue(c, guild_id, config_id, "publish", {})
            if value["self_destruct_at"]: self._schedule(c,guild_id,config_id,None,None,"self_destruct",value["self_destruct_at"])
            self.audit(guild_id, config_id, "config_created", "success", actor_id=actor_id, _conn=c)
            return self.message(guild_id, config_id, _conn=c) or {}

    def update_message(self, guild_id: int, config_id: int, value: dict[str, Any], expected_revision: int, actor_id: int | None = None) -> dict[str, Any]:
        now = int(time.time())
        with self.connection() as c:
            row = c.execute("SELECT revision,source FROM reaction_role_messages_v2 WHERE guild_id=%s AND id=%s FOR UPDATE", (guild_id,config_id)).fetchone()
            if not row: raise KeyError(config_id)
            if int(row["revision"]) != expected_revision: raise RuntimeError("revision_conflict")
            self._check_link_group(c, guild_id, value.get('link_group_id'))
            if row["source"] == "external" and value["source"] != "external": raise ValueError("source_immutable")
            c.execute("""UPDATE reaction_role_messages_v2 SET channel_id=%s,message_id=%s,name=%s,behavior_type=%s,locked=%s,access_policy=%s,selection_limit=%s,temp_duration_seconds=%s,self_destruct_at=%s,embed_json=%s,link_group_id=%s,enabled=%s,status='pending',last_error=NULL,revision=revision+1,updated_at=%s WHERE id=%s""",
                (value["channel_id"],value["message_id"],value["name"],value["behavior_type"],int(value["locked"]),value["access_policy"],value["selection_limit"],value["temp_duration_seconds"],value["self_destruct_at"],json.dumps(value["embed"],ensure_ascii=False),value["link_group_id"],int(value["enabled"]),now,config_id))
            self._replace_children(c, config_id, value); self._queue(c,guild_id,config_id,"sync",{})
            c.execute("DELETE FROM reaction_role_schedules WHERE message_config_id=%s AND kind='self_destruct' AND state='pending'",(config_id,))
            if value["self_destruct_at"]:self._schedule(c,guild_id,config_id,None,None,"self_destruct",value["self_destruct_at"])
        self.audit(guild_id,config_id,"config_updated","success",actor_id=actor_id)
        return self.message(guild_id,config_id) or {}

    def delete_message(self, guild_id: int, config_id: int, *, recoverable: bool, actor_id: int | None = None, expected_revision: int | None = None, queue_delete: bool = False) -> None:
        now = int(time.time())
        with self.connection() as c:
            current = c.execute('SELECT revision FROM reaction_role_messages_v2 WHERE guild_id=%s AND id=%s FOR UPDATE', (guild_id, config_id)).fetchone()
            if expected_revision is not None and (current is None or current['revision'] != expected_revision):
                raise RuntimeError('revision_conflict')
            if current is None:
                return
            item = self.message(guild_id, config_id, _conn=c)
            if queue_delete:
                self._queue(c, guild_id, None, 'delete', {'channel_id': item['channel_id'], 'message_id': item.get('message_id'), 'source': item['source']})
            if recoverable and item.get("message_id"):
                snapshot = {key:value for key,value in item.items() if key not in {"last_error"}}
                c.execute('INSERT INTO reaction_role_recovery VALUES(%s,%s,%s,%s,%s) ON CONFLICT(guild_id,deleted_message_id) DO UPDATE SET snapshot_json=excluded.snapshot_json,created_at=excluded.created_at,expires_at=excluded.expires_at', (guild_id,item["message_id"],json.dumps(snapshot,ensure_ascii=False),now,now+604800))
            self._detach_expiries(c, config_id)
            c.execute("DELETE FROM reaction_role_messages_v2 WHERE guild_id=%s AND id=%s", (guild_id,config_id))
        self.audit(guild_id,None,"message_deleted","success",actor_id=actor_id,details={"message_id":item.get("message_id"),"recoverable":recoverable})

    def recovery(self, guild_id: int, message_id: int) -> dict[str, Any] | None:
        with self.connection() as c:
            row=c.execute("SELECT snapshot_json FROM reaction_role_recovery WHERE guild_id=%s AND deleted_message_id=%s AND expires_at>%s",(guild_id,message_id,int(time.time()))).fetchone()
        return json.loads(row["snapshot_json"]) if row else None

    def consume_recovery(self,guild_id:int,message_id:int,*,_conn=None)->None:
        with (nullcontext(_conn) if _conn is not None else self.connection()) as c:
            c.execute("DELETE FROM reaction_role_recovery WHERE guild_id=%s AND deleted_message_id=%s",(guild_id,message_id))

    def restore_message(self, guild_id: int, message_id: int, value: dict[str, Any], actor_id: int | None,
                        *, expected_snapshot: dict[str, Any]) -> dict[str, Any]:
        with self.connection() as c:
            lock_resource(c, 'reaction-role-settings', guild_id)
            row = c.execute('SELECT snapshot_json FROM reaction_role_recovery WHERE guild_id=%s AND deleted_message_id=%s AND expires_at>%s FOR UPDATE',
                            (guild_id, message_id, int(time.time()))).fetchone()
            if row is None:
                raise ValueError('recovery_not_found')
            if json.loads(row['snapshot_json']) != expected_snapshot:
                raise RuntimeError('recovery_conflict')
            created = self.create_message(guild_id, value, actor_id, _conn=c)
            self.consume_recovery(guild_id, message_id, _conn=c)
            return created

    def recoveries(self,guild_id:int)->list[dict[str,Any]]:
        now=int(time.time())
        with self.connection() as c:rows=c.execute("SELECT deleted_message_id,created_at,expires_at FROM reaction_role_recovery WHERE guild_id=%s AND expires_at>%s ORDER BY created_at DESC",(guild_id,now)).fetchall()
        return [dict(row) for row in rows]

    def create_link_group(self, guild_id: int, name: str, config_ids: list[int]) -> dict[str, Any]:
        if len(set(config_ids)) < 2:
            raise ValueError("link_members")
        now=int(time.time())
        with self.connection() as c:
            rows=c.execute(f"SELECT id,behavior_type,link_group_id FROM reaction_role_messages_v2 WHERE guild_id=%s AND id IN ({','.join('%s' for _ in config_ids)}) ORDER BY id FOR UPDATE",(guild_id,*config_ids)).fetchall()
            if len(rows)<2 or len(rows)!=len(set(config_ids)): raise ValueError("link_members")
            if any(row["behavior_type"] not in {"normal","unique","temp"} or row["link_group_id"] is not None for row in rows): raise ValueError("link_conflict")
            cursor=c.execute('INSERT INTO reaction_role_link_groups(guild_id,name,created_at,updated_at) VALUES(%s,%s,%s,%s) RETURNING id',(guild_id,name[:100] or "Link Group",now,now)); inserted = cursor.fetchone(); group_id=int(inserted["id"])
            c.execute(f"UPDATE reaction_role_messages_v2 SET link_group_id=%s,revision=revision+1,updated_at=%s WHERE guild_id=%s AND id IN ({','.join('%s' for _ in config_ids)})",(group_id,now,guild_id,*config_ids))
        return self.link_group(guild_id,group_id) or {}

    def link_group(self,guild_id:int,group_id:int)->dict[str,Any]|None:
        with self.connection() as c:
            row=c.execute("SELECT * FROM reaction_role_link_groups WHERE guild_id=%s AND id=%s",(guild_id,group_id)).fetchone()
            members=c.execute("SELECT id FROM reaction_role_messages_v2 WHERE guild_id=%s AND link_group_id=%s ORDER BY id",(guild_id,group_id)).fetchall() if row else []
        return {**dict(row),"message_ids":[item["id"] for item in members]} if row else None

    def link_groups(self,guild_id:int)->list[dict[str,Any]]:
        with self.connection() as c: ids=[row["id"] for row in c.execute("SELECT id FROM reaction_role_link_groups WHERE guild_id=%s ORDER BY id",(guild_id,)).fetchall()]
        return [item for group_id in ids if (item:=self.link_group(guild_id,group_id))]

    def dissolve_link_group(self,guild_id:int,group_id:int)->None:
        with self.connection() as c:
            c.execute("UPDATE reaction_role_messages_v2 SET link_group_id=NULL,revision=revision+1 WHERE guild_id=%s AND link_group_id=%s",(guild_id,group_id)); c.execute("DELETE FROM reaction_role_link_groups WHERE guild_id=%s AND id=%s",(guild_id,group_id))

    def assignments(self, user_id: int, *, config_id: int | None = None, link_group_id: int | None = None, guild_id: int | None = None) -> list[dict[str,Any]]:
        with self.connection() as c:
            if link_group_id is not None:
                rows=c.execute("""SELECT a.* FROM reaction_role_assignments a JOIN reaction_role_messages_v2 m ON m.id=a.message_config_id
                    JOIN reaction_role_link_groups g ON g.id=m.link_group_id AND g.guild_id=m.guild_id
                    WHERE a.user_id=%s AND a.state='active' AND m.link_group_id=%s AND (%s::bigint IS NULL OR m.guild_id=%s)""",(user_id,link_group_id,guild_id,guild_id)).fetchall()
            else: rows=c.execute("SELECT * FROM reaction_role_assignments WHERE user_id=%s AND message_config_id=%s AND state='active'",(user_id,config_id)).fetchall()
        return [dict(row) for row in rows]

    def binding_receipt(self,config_id:int,user_id:int)->dict[str,Any]|None:
        with self.connection() as c: row=c.execute("SELECT * FROM reaction_role_binding_receipts WHERE message_config_id=%s AND user_id=%s",(config_id,user_id)).fetchone()
        return dict(row) if row else None

    def reset_binding(self,config_id:int,user_id:int, *, guild_id:int|None=None)->bool:
        with self.connection() as c: cursor=c.execute("""DELETE FROM reaction_role_binding_receipts r USING reaction_role_messages_v2 m
            WHERE r.message_config_id=m.id AND r.message_config_id=%s AND r.user_id=%s AND (%s::bigint IS NULL OR m.guild_id=%s)""",(config_id,user_id,guild_id,guild_id))
        return cursor.rowcount>0

    def consume_self_destruct(self, guild_id: int, config_id: int, due_at: int, job=None) -> None:
        with self.connection() as c:
            self._guard_job(c, job, schedule=True)
            current = c.execute('SELECT * FROM reaction_role_messages_v2 WHERE guild_id=%s AND id=%s FOR UPDATE', (guild_id, config_id)).fetchone()
            if current is None or current['source'] != 'bot' or current['self_destruct_at'] != due_at:
                return
            self._queue(c, guild_id, None, 'delete', {'channel_id': current['channel_id'], 'message_id': current['message_id'], 'source': 'bot'})
            self._detach_expiries(c, config_id)
            c.execute('DELETE FROM reaction_role_messages_v2 WHERE guild_id=%s AND id=%s', (guild_id, config_id))
            self.audit(guild_id, None, 'message_deleted', 'success', details={'message_id': current['message_id'], 'recoverable': False}, _conn=c)

    def temporary_expiry(self, item: dict, *, lease=None) -> dict | None:
        with self.connection() as c:
            if lease:
                lease.guard(c)
            self._guard_job(c, item, schedule=True)
            schedule = c.execute("SELECT * FROM reaction_role_schedules WHERE id=%s AND guild_id=%s AND kind='temp_role'", (item['id'], item['guild_id'])).fetchone()
            if (schedule is None or schedule['state'] not in {'pending', 'retry', 'processing'}
                    or schedule['scheduled_for'] != item.get('scheduled_for') or schedule['scheduled_for'] is None
                    or schedule['selection_generation'] != item.get('selection_generation')):
                return None
            if schedule['selection_generation'] is None:
                raise ValueError('Selection generation unavailable; reconciliation required')
            if schedule['mapping_id'] is not None:
                active = c.execute("""SELECT 1 FROM reaction_role_assignments WHERE message_config_id=%s AND mapping_id=%s
                    AND user_id=%s AND state='active' AND expires_at=%s AND generation=%s""",
                    (schedule['message_config_id'],schedule['mapping_id'],item['user_id'],schedule['scheduled_for'],schedule['selection_generation'])).fetchone()
                if not active:
                    return None
            selected = c.execute("""SELECT 1 FROM reaction_role_assignments a JOIN reaction_role_messages_v2 m ON m.id=a.message_config_id
                WHERE m.guild_id=%s AND a.user_id=%s AND a.role_id=%s AND a.state='active' AND a.generation<>%s
                AND (a.expires_at IS NULL OR EXISTS (SELECT 1 FROM reaction_role_schedules owned
                    WHERE owned.guild_id=m.guild_id AND owned.user_id=a.user_id AND owned.selection_generation=a.generation
                    AND owned.kind='temp_role' AND NOT owned.cleanup_only AND owned.state IN ('pending','retry','processing'))) LIMIT 1""",
                (item['guild_id'],item['user_id'],schedule['role_id'],schedule['selection_generation'])).fetchone()
            return {**dict(schedule), 'remove_role': not schedule['cleanup_only'] and not selected}

    def finish_temporary_expiry(self, item, expiry, *, lease):
        with self.connection() as c:
            lease.guard(c)
            self._guard_job(c, item, schedule=True)
            if expiry['mapping_id'] is not None:
                c.execute("""UPDATE reaction_role_assignments SET state='removed',updated_at=%s WHERE message_config_id=%s
                    AND mapping_id=%s AND user_id=%s AND generation=%s AND expires_at=%s""",
                    (int(time.time()),expiry['message_config_id'],expiry['mapping_id'],item['user_id'],expiry['selection_generation'],expiry['scheduled_for']))

    def cleanup_current(self, item):
        payload = item['payload']
        if payload.get('selection_generation') is None:
            raise ValueError('Cleanup selection generation unavailable; reconciliation required')
        with self.connection() as c:
            self._guard_job(c, item)
            current = c.execute("""SELECT a.generation FROM reaction_role_assignments a JOIN reaction_role_messages_v2 m ON m.id=a.message_config_id
                WHERE m.guild_id=%s AND a.message_config_id=%s AND a.mapping_id=%s AND a.user_id=%s""",
                (item['guild_id'],payload['config_id'],payload['mapping_id'],payload['user_id'])).fetchone()
            return current is not None and current['generation'] == payload['selection_generation']

    def queue_reaction_removal(self, config, mapping, user_id, *, lease, event='remove'):
        if event not in {'add', 'remove'}:
            raise ValueError('Invalid reaction event')
        action = f'reconcile_{event}'
        with self.connection() as c:
            lease.guard(c)
            row = c.execute('SELECT generation FROM reaction_role_assignments WHERE message_config_id=%s AND mapping_id=%s AND user_id=%s',
                (config['id'], mapping['id'], user_id)).fetchone()
            payload = {
                'revision': config['revision'], 'mapping_id': mapping['id'], 'user_id': user_id,
                'selection_generation': row['generation'] if row else None}
            duplicate = c.execute("""SELECT 1 FROM reaction_role_outbox WHERE guild_id=%s AND message_config_id=%s
                AND action=%s AND state IN ('pending','retry','processing') AND payload_json::jsonb=%s::jsonb""",
                (config['guild_id'], config['id'], action, json.dumps(payload))).fetchone()
            if not duplicate:
                self._queue(c, config['guild_id'], config['id'], action, payload)

    def selection_generation(self, config_id, mapping_id, user_id):
        with self.connection() as c:
            row = c.execute('SELECT generation FROM reaction_role_assignments WHERE message_config_id=%s AND mapping_id=%s AND user_id=%s',
                (config_id, mapping_id, user_id)).fetchone()
        return row['generation'] if row else None

    def queue_member_reconciliation(self, config, mapping, user_id, event, *, selection_generation, competing_owner_token):
        with self.connection() as c:
            lock_resource(c, 'reaction-role-reconcile', f'{config["guild_id"]}:{user_id}')
            payload = {'revision': config['revision'], 'mapping_id': mapping['id'], 'user_id': user_id,
                'event': event, 'selection_generation': selection_generation, 'predecessor_lease_token': competing_owner_token}
            duplicate = c.execute("""SELECT 1 FROM reaction_role_outbox WHERE guild_id=%s AND message_config_id=%s
                AND action='reconcile_selection' AND state IN ('pending','retry','processing') AND payload_json::jsonb=%s::jsonb""",
                (config['guild_id'], config['id'], json.dumps(payload))).fetchone()
            if not duplicate:
                self._queue(c, config['guild_id'], config['id'], 'reconcile_selection', payload)

    def _reaction_generation_current(self, c, item):
        payload = item['payload']
        row = c.execute('SELECT generation FROM reaction_role_assignments WHERE message_config_id=%s AND mapping_id=%s AND user_id=%s',
            (item['message_config_id'], payload['mapping_id'], payload['user_id'])).fetchone()
        generation = row['generation'] if row else None
        if generation == payload['selection_generation']:
            return True
        if item['action'] != 'reconcile_selection' or payload.get('predecessor_lease_token') is None:
            return False
        predecessor = c.execute("""SELECT details_json FROM reaction_role_events WHERE guild_id=%s AND user_id=%s
            AND message_config_id=%s AND event_type='role_change' AND result='committed'
            AND details_json::jsonb->>'member_lease_token'=%s ORDER BY id DESC LIMIT 1""",
            (item['guild_id'], payload['user_id'], item['message_config_id'], payload['predecessor_lease_token'])).fetchone()
        if predecessor is None:
            return False
        detail = json.loads(predecessor['details_json'])
        return detail['mapping_id'] == payload['mapping_id'] and generation is not None and detail.get('committed_generation') == generation

    def reaction_removal_current(self, item, *, lease):
        payload = item['payload']
        with self.connection() as c:
            lease.guard(c)
            self._guard_job(c, item)
            config = c.execute('SELECT revision FROM reaction_role_messages_v2 WHERE guild_id=%s AND id=%s',
                (item['guild_id'], item['message_config_id'])).fetchone()
            if config is None or config['revision'] != payload['revision']:
                return False
            return self._reaction_generation_current(c, item)

    def begin_role_change(self, guild_id: int, user_id: int, detail: dict, *, lease=None) -> dict:
        if lease is not None:
            detail = {**detail, 'member_lease_token': lease.token}
        now = int(time.time())
        with self.connection() as c:
            if lease:
                lease.guard(c)
            lock_resource(c, "reaction-role-user", f"{guild_id}:{user_id}")
            pending = c.execute("SELECT 1 FROM reaction_role_events WHERE guild_id=%s AND user_id=%s AND event_type='role_change' AND result IN ('pending','compensation_failed')", (guild_id, user_id)).fetchone()
            if pending:
                raise RuntimeError('role_recovery_required')
            current = c.execute('SELECT revision FROM reaction_role_messages_v2 WHERE guild_id=%s AND id=%s FOR UPDATE', (guild_id, detail['config_id'])).fetchone()
            if current is None or current['revision'] != detail['revision']:
                raise RuntimeError('revision_conflict')
            cursor = c.execute("INSERT INTO reaction_role_events(guild_id,message_config_id,user_id,event_type,result,details_json,created_at,expires_at) VALUES(%s,%s,%s,'role_change','pending',%s,%s,%s) RETURNING id",
                (guild_id, detail['config_id'], user_id, json.dumps(detail), now, now + 90 * 86400)); inserted = cursor.fetchone()
        return {'id': int(inserted["id"]), 'guild_id': guild_id, 'user_id': user_id, 'detail': detail, 'created_at': now}

    def pending_role_changes(self, guild_id: int) -> list[dict]:
        with self.connection() as c:
            rows = c.execute("SELECT * FROM reaction_role_events WHERE guild_id=%s AND event_type='role_change' AND result IN ('pending','compensation_failed') ORDER BY id", (guild_id,)).fetchall()
        return [{**dict(row), 'detail': json.loads(row['details_json'])} for row in rows]

    def role_capacity(self, guild_id: int, role_id: int) -> int | None:
        with self.connection() as c:
            row = c.execute("""SELECT min(r.max_members) AS capacity FROM reaction_role_mappings_v2 r
                JOIN reaction_role_messages_v2 m ON m.id=r.message_config_id WHERE m.guild_id=%s AND r.role_id=%s""",
                (guild_id, role_id)).fetchone()
        return row['capacity']

    def role_change_finished(self, operation_id: int) -> bool:
        with self.connection() as c:
            row = c.execute('SELECT result FROM reaction_role_events WHERE id=%s', (operation_id,)).fetchone()
        return row is not None and row['result'] in {'committed', 'rolled_back'}

    def fail_role_compensation(self, operation_id: int, reason: str, *, lease=None) -> None:
        with self.connection() as c:
            if lease:
                lease.guard(c)
            c.execute("UPDATE reaction_role_events SET result='compensation_failed',reason=%s WHERE id=%s AND result IN ('pending','compensation_failed')", (reason[:500], operation_id))

    def finish_role_rollback(self, operation_id: int, *, lease=None) -> None:
        with self.connection() as c:
            if lease:
                lease.guard(c)
            c.execute("UPDATE reaction_role_events SET result='rolled_back' WHERE id=%s AND result IN ('pending','compensation_failed')", (operation_id,))

    def commit_role_change(self, operation: dict, *, lease=None, removal_job=None) -> None:
        detail, now = operation['detail'], int(time.time())
        with self.connection() as c:
            if lease:
                lease.guard(c)
            if removal_job is not None:
                self._guard_job(c, removal_job)
                if not self._reaction_generation_current(c, removal_job):
                    raise RuntimeError('Removal selection changed')
            receipt = c.execute('SELECT result FROM reaction_role_events WHERE id=%s FOR UPDATE', (operation['id'],)).fetchone()
            if receipt is None or receipt['result'] != 'pending':
                raise RuntimeError('role_operation_conflict')
            current = c.execute('SELECT revision FROM reaction_role_messages_v2 WHERE guild_id=%s AND id=%s FOR UPDATE', (operation['guild_id'], detail['config_id'])).fetchone()
            if current is None or current['revision'] != detail['revision']:
                raise RuntimeError('revision_conflict')
            if detail['operation'] == 'remove':
                c.execute("UPDATE reaction_role_assignments SET state='removed',updated_at=%s WHERE message_config_id=%s AND mapping_id=%s AND user_id=%s",
                    (now, detail['config_id'], detail['mapping_id'], operation['user_id']))
            else:
                for previous in detail['conflicts']:
                    c.execute("UPDATE reaction_role_assignments SET state='removed',updated_at=%s WHERE message_config_id=%s AND mapping_id=%s AND user_id=%s",
                        (now, previous['message_config_id'], previous['mapping_id'], operation['user_id']))
                assigned = c.execute("""INSERT INTO reaction_role_assignments(message_config_id,mapping_id,user_id,role_id,state,expires_at,created_at,updated_at)
                    VALUES(%s,%s,%s,%s,'active',%s,%s,%s) ON CONFLICT(message_config_id,mapping_id,user_id) DO UPDATE SET
                    state='active',expires_at=excluded.expires_at,updated_at=excluded.updated_at,generation=nextval('reaction_role_selection_generation') RETURNING generation""",
                    (detail['config_id'],detail['mapping_id'],operation['user_id'],detail['role_id'],detail['expires_at'],now,now)).fetchone()
                c.execute("UPDATE reaction_role_events SET details_json=jsonb_set(details_json::jsonb,'{committed_generation}',to_jsonb(%s::bigint))::text WHERE id=%s",
                    (assigned['generation'], operation['id']))
                if detail['binding']:
                    c.execute('INSERT INTO reaction_role_binding_receipts VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING', (detail['config_id'], operation['user_id'], detail['mapping_id'], now))
                if detail['expires_at']:
                    self._schedule(c, operation['guild_id'], detail['config_id'], detail['mapping_id'], operation['user_id'], 'temp_role', detail['expires_at'], role_id=detail['role_id'])
            if detail['operation'] == 'add':
                for previous in detail['conflicts']:
                    target = c.execute("""SELECT m.channel_id,m.message_id,r.emoji_display AS emoji FROM reaction_role_messages_v2 m
                        JOIN reaction_role_mappings_v2 r ON r.message_config_id=m.id WHERE m.id=%s AND r.id=%s""",
                        (previous['message_config_id'], previous['mapping_id'])).fetchone()
                    if target and target['message_id']:
                        self._queue(c, operation['guild_id'], None, 'clear_selection', {**dict(target), 'user_id': operation['user_id'],
                            'config_id': previous['message_config_id'], 'mapping_id': previous['mapping_id'], 'selection_generation': previous.get('generation')})
                if detail['verify'] and detail['message_id']:
                    self._queue(c, operation['guild_id'], None, 'clear_selection', {key: detail[key] for key in ('channel_id', 'message_id', 'emoji')} |
                        {'user_id': operation['user_id'], 'config_id': detail['config_id'], 'mapping_id': detail['mapping_id'], 'selection_generation': assigned['generation']})
            c.execute("UPDATE reaction_role_events SET result='committed' WHERE id=%s", (operation['id'],))

    def activate_assignment(self,guild_id:int,config_id:int,mapping_id:int,user_id:int,role_id:int,expires_at:int|None,binding:bool=False)->None:
        now=int(time.time())
        with self.connection() as c:
            c.execute("""INSERT INTO reaction_role_assignments(message_config_id,mapping_id,user_id,role_id,state,expires_at,created_at,updated_at)
                VALUES(%s,%s,%s,%s,'active',%s,%s,%s) ON CONFLICT(message_config_id,mapping_id,user_id) DO UPDATE SET
                state='active',expires_at=excluded.expires_at,updated_at=excluded.updated_at,generation=nextval('reaction_role_selection_generation')""",(config_id,mapping_id,user_id,role_id,expires_at,now,now))
            if binding: c.execute('INSERT INTO reaction_role_binding_receipts VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',(config_id,user_id,mapping_id,now))
            if expires_at: self._schedule(c,guild_id,config_id,mapping_id,user_id,"temp_role",expires_at,role_id=role_id)

    def deactivate_assignment(self,config_id:int,mapping_id:int,user_id:int, *, lease=None)->None:
        with self.connection() as c:
            if lease:
                lease.guard(c)
            c.execute("UPDATE reaction_role_assignments SET state='removed',updated_at=%s WHERE message_config_id=%s AND mapping_id=%s AND user_id=%s",(int(time.time()),config_id,mapping_id,user_id))

    @staticmethod
    def _schedule(c:Connection,guild_id:int,config_id:int|None,mapping_id:int|None,user_id:int|None,kind:str,due_at:int,*,role_id:int|None=None)->None:
        now = int(time.time())
        generation = c.execute('SELECT generation FROM reaction_role_assignments WHERE message_config_id=%s AND mapping_id=%s AND user_id=%s', (config_id,mapping_id,user_id)).fetchone() if kind == 'temp_role' else None
        scheduled = c.execute("""INSERT INTO reaction_role_schedules(guild_id,message_config_id,mapping_id,user_id,kind,due_at,scheduled_for,role_id,created_at,selection_generation)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(kind,message_config_id,mapping_id,user_id,scheduled_for) DO UPDATE SET
                due_at=excluded.due_at,role_id=excluded.role_id,selection_generation=excluded.selection_generation,cleanup_only=false,state='pending',attempts=0,
                last_error=NULL,completed_at=NULL,lease_owner=NULL,lease_token=NULL,lease_until=NULL
            RETURNING id""",(guild_id,config_id,mapping_id,user_id,kind,due_at,due_at,role_id,now,generation['generation'] if generation else None)).fetchone()
        if kind == 'temp_role':
            c.execute("""UPDATE reaction_role_schedules SET cleanup_only=true,
                state=CASE WHEN mapping_id IS NOT NULL THEN 'pending' ELSE 'done' END,
                due_at=CASE WHEN mapping_id IS NOT NULL THEN scheduled_for ELSE due_at END,
                completed_at=CASE WHEN mapping_id IS NOT NULL THEN NULL ELSE %s END,
                last_error='Superseded by a newer Reaction Role selection',lease_owner=NULL,lease_token=NULL,lease_until=NULL
                WHERE guild_id=%s AND user_id=%s AND role_id=%s AND kind='temp_role'
                AND id<>%s AND state IN ('pending','retry','processing')""", (now,guild_id,user_id,role_id,scheduled['id']))

    @staticmethod
    def _queue(c:Connection,guild_id:int,config_id:int|None,action:str,payload:dict[str,Any])->None:
        c.execute("INSERT INTO reaction_role_outbox(guild_id,message_config_id,action,payload_json,created_at) VALUES(%s,%s,%s,%s,%s)",(guild_id,config_id,action,json.dumps(payload),int(time.time())))

    def queue_action(self,guild_id:int,config_id:int|None,action:str,payload:dict[str,Any]|None=None)->None:
        with self.connection() as c: self._queue(c,guild_id,config_id,action,payload or {})



    def set_discord_message(self,config_id:int,message_id:int,status:str="active",error:str|None=None,*,job=None)->None:
        with self.connection() as c:
            self._guard_job(c, job)
            c.execute("UPDATE reaction_role_messages_v2 SET message_id=%s,status=%s,last_error=%s,updated_at=%s WHERE id=%s",(message_id,status,error,int(time.time()),config_id))

    def set_delivery_status(self,config_id:int,status:str,error:str|None=None,*,job=None)->None:
        with self.connection() as c:
            self._guard_job(c, job)
            c.execute("UPDATE reaction_role_messages_v2 SET status=%s,last_error=%s,updated_at=%s WHERE id=%s",(status,error[:500] if error else None,int(time.time()),config_id))

    def move_message(self,guild_id:int,config_id:int,channel_id:int,message_id:int,source:str,expected_revision:int,actor_id:int|None=None,*,job=None)->dict[str,Any]:
        with self.connection() as c:
            self._guard_job(c, job)
            row=c.execute("SELECT revision,channel_id,message_id,source FROM reaction_role_messages_v2 WHERE guild_id=%s AND id=%s FOR UPDATE",(guild_id,config_id)).fetchone()
            if not row:raise KeyError(config_id)
            if int(row["revision"])!=expected_revision:raise RuntimeError("revision_conflict")
            c.execute("UPDATE reaction_role_messages_v2 SET channel_id=%s,message_id=%s,source=%s,status='active',last_error=NULL,revision=revision+1,updated_at=%s WHERE id=%s",(channel_id,message_id,source,int(time.time()),config_id))
            if row['source'] == 'bot' and row['message_id'] and (row['channel_id'], row['message_id']) != (channel_id, message_id):
                self._queue(c, guild_id, None, 'delete', {'channel_id': row['channel_id'], 'message_id': row['message_id'], 'source': 'bot'})
        self.audit(guild_id,config_id,"message_moved","success",actor_id=actor_id,details={"channel_id":channel_id,"message_id":message_id})
        return self.message(guild_id,config_id) or {}



    def audit(self,guild_id:int,config_id:int|None,event_type:str,result:str,*,user_id:int|None=None,actor_id:int|None=None,emoji_key:str|None=None,role_id:int|None=None,reason:str|None=None,details:dict[str,Any]|None=None,_conn=None)->int:
        now=int(time.time())
        with (nullcontext(_conn) if _conn is not None else self.connection()) as c: cursor=c.execute('INSERT INTO reaction_role_events(guild_id,message_config_id,user_id,actor_id,emoji_key,role_id,event_type,result,reason,details_json,created_at,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',(guild_id,config_id,user_id,actor_id,emoji_key,role_id,event_type,result,reason,json.dumps(details or {},ensure_ascii=False),now,now+90*86400)); inserted = cursor.fetchone()
        return int(inserted["id"])

    def events(self,guild_id:int,limit:int=100)->list[dict[str,Any]]:
        with self.connection() as c: rows=c.execute("SELECT * FROM reaction_role_events WHERE guild_id=%s ORDER BY id DESC LIMIT %s",(guild_id,max(1,min(limit,500)))).fetchall()
        return [{**dict(row),"details":json.loads(row["details_json"])} for row in rows]

    def maintain(self)->dict[str,int]:
        now=int(time.time())
        with self.connection() as c:
            events=c.execute("DELETE FROM reaction_role_events WHERE expires_at<=%s AND NOT(event_type='role_change' AND result IN ('pending','compensation_failed'))",(now,)).rowcount
            recovery=c.execute("DELETE FROM reaction_role_recovery WHERE expires_at<=%s",(now,)).rowcount
        return {"events":events,"recovery":recovery}
