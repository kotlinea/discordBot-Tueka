"""PostgreSQL repository for Reaction Roles."""
from __future__ import annotations

import json
from contextlib import nullcontext
import time
from jobs import QueueRepository, QueueSpec
from jobs.catalog import QUEUE_SPECS
from database import Connection, lock_resource, require_current, transaction
from typing import Any


class ReactionRoleRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        require_current(self.database_url)
        self.outbox_jobs = QueueRepository(self.database_url, QUEUE_SPECS['reaction_role_outbox'])
        self.schedule_jobs = QueueRepository(self.database_url, QUEUE_SPECS['reaction_role_schedules'])

    def connection(self):
        return transaction(self.database_url)

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

    def create_message(self, guild_id: int, value: dict[str, Any], actor_id: int | None = None) -> dict[str, Any]:
        now = int(time.time())
        with self.connection() as c:
            lock_resource(c, "reaction-role-settings", guild_id)
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
        self.audit(guild_id, config_id, "config_created", "success", actor_id=actor_id)
        return self.message(guild_id, config_id) or {}

    def update_message(self, guild_id: int, config_id: int, value: dict[str, Any], expected_revision: int, actor_id: int | None = None) -> dict[str, Any]:
        now = int(time.time())
        with self.connection() as c:
            row = c.execute("SELECT revision,source FROM reaction_role_messages_v2 WHERE guild_id=%s AND id=%s FOR UPDATE", (guild_id,config_id)).fetchone()
            if not row: raise KeyError(config_id)
            if int(row["revision"]) != expected_revision: raise RuntimeError("revision_conflict")
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
            c.execute("DELETE FROM reaction_role_messages_v2 WHERE guild_id=%s AND id=%s", (guild_id,config_id))
        self.audit(guild_id,None,"message_deleted","success",actor_id=actor_id,details={"message_id":item.get("message_id"),"recoverable":recoverable})

    def recovery(self, guild_id: int, message_id: int) -> dict[str, Any] | None:
        with self.connection() as c:
            row=c.execute("SELECT snapshot_json FROM reaction_role_recovery WHERE guild_id=%s AND deleted_message_id=%s AND expires_at>%s",(guild_id,message_id,int(time.time()))).fetchone()
        return json.loads(row["snapshot_json"]) if row else None

    def consume_recovery(self,guild_id:int,message_id:int)->None:
        with self.connection() as c:c.execute("DELETE FROM reaction_role_recovery WHERE guild_id=%s AND deleted_message_id=%s",(guild_id,message_id))

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

    def assignments(self, user_id: int, *, config_id: int | None = None, link_group_id: int | None = None) -> list[dict[str,Any]]:
        with self.connection() as c:
            if link_group_id is not None:
                rows=c.execute("""SELECT a.* FROM reaction_role_assignments a JOIN reaction_role_messages_v2 m ON m.id=a.message_config_id WHERE a.user_id=%s AND a.state='active' AND m.link_group_id=%s""",(user_id,link_group_id)).fetchall()
            else: rows=c.execute("SELECT * FROM reaction_role_assignments WHERE user_id=%s AND message_config_id=%s AND state='active'",(user_id,config_id)).fetchall()
        return [dict(row) for row in rows]

    def binding_receipt(self,config_id:int,user_id:int)->dict[str,Any]|None:
        with self.connection() as c: row=c.execute("SELECT * FROM reaction_role_binding_receipts WHERE message_config_id=%s AND user_id=%s",(config_id,user_id)).fetchone()
        return dict(row) if row else None

    def reset_binding(self,config_id:int,user_id:int)->bool:
        with self.connection() as c: cursor=c.execute("DELETE FROM reaction_role_binding_receipts WHERE message_config_id=%s AND user_id=%s",(config_id,user_id))
        return cursor.rowcount>0

    def begin_role_change(self, guild_id: int, user_id: int, detail: dict, *, lease=None) -> dict:
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

    def commit_role_change(self, operation: dict, *, lease=None) -> None:
        detail, now = operation['detail'], int(time.time())
        with self.connection() as c:
            if lease:
                lease.guard(c)
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
                c.execute("""INSERT INTO reaction_role_assignments VALUES(%s,%s,%s,%s, 'active',%s,%s,%s)
                    ON CONFLICT(message_config_id,mapping_id,user_id) DO UPDATE SET state='active',expires_at=excluded.expires_at,updated_at=excluded.updated_at""",
                    (detail['config_id'], detail['mapping_id'], operation['user_id'], detail['role_id'], detail['expires_at'], now, now))
                if detail['binding']:
                    c.execute('INSERT INTO reaction_role_binding_receipts VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING', (detail['config_id'], operation['user_id'], detail['mapping_id'], now))
                if detail['expires_at']:
                    self._schedule(c, operation['guild_id'], detail['config_id'], detail['mapping_id'], operation['user_id'], 'temp_role', detail['expires_at'])
            if detail['operation'] == 'add':
                for previous in detail['conflicts']:
                    target = c.execute("""SELECT m.channel_id,m.message_id,r.emoji_display AS emoji FROM reaction_role_messages_v2 m
                        JOIN reaction_role_mappings_v2 r ON r.message_config_id=m.id WHERE m.id=%s AND r.id=%s""",
                        (previous['message_config_id'], previous['mapping_id'])).fetchone()
                    if target and target['message_id']:
                        self._queue(c, operation['guild_id'], None, 'clear_selection', {**dict(target), 'user_id': operation['user_id']})
                if detail['verify'] and detail['message_id']:
                    self._queue(c, operation['guild_id'], None, 'clear_selection', {key: detail[key] for key in ('channel_id', 'message_id', 'emoji')} | {'user_id': operation['user_id']})
            c.execute("UPDATE reaction_role_events SET result='committed' WHERE id=%s", (operation['id'],))

    def activate_assignment(self,guild_id:int,config_id:int,mapping_id:int,user_id:int,role_id:int,expires_at:int|None,binding:bool=False)->None:
        now=int(time.time())
        with self.connection() as c:
            c.execute("""INSERT INTO reaction_role_assignments VALUES(%s,%s,%s,%s, 'active',%s,%s,%s) ON CONFLICT(message_config_id,mapping_id,user_id) DO UPDATE SET state='active',expires_at=excluded.expires_at,updated_at=excluded.updated_at""",(config_id,mapping_id,user_id,role_id,expires_at,now,now))
            if binding: c.execute('INSERT INTO reaction_role_binding_receipts VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',(config_id,user_id,mapping_id,now))
            if expires_at: self._schedule(c,guild_id,config_id,mapping_id,user_id,"temp_role",expires_at)

    def deactivate_assignment(self,config_id:int,mapping_id:int,user_id:int, *, lease=None)->None:
        with self.connection() as c:
            if lease:
                lease.guard(c)
            c.execute("UPDATE reaction_role_assignments SET state='removed',updated_at=%s WHERE message_config_id=%s AND mapping_id=%s AND user_id=%s",(int(time.time()),config_id,mapping_id,user_id))

    @staticmethod
    def _schedule(c:Connection,guild_id:int,config_id:int|None,mapping_id:int|None,user_id:int|None,kind:str,due_at:int)->None:
        c.execute('INSERT INTO reaction_role_schedules(guild_id,message_config_id,mapping_id,user_id,kind,due_at,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(guild_id,config_id,mapping_id,user_id,kind,due_at,int(time.time())))

    @staticmethod
    def _queue(c:Connection,guild_id:int,config_id:int|None,action:str,payload:dict[str,Any])->None:
        c.execute("INSERT INTO reaction_role_outbox(guild_id,message_config_id,action,payload_json,created_at) VALUES(%s,%s,%s,%s,%s)",(guild_id,config_id,action,json.dumps(payload),int(time.time())))

    def queue_action(self,guild_id:int,config_id:int|None,action:str,payload:dict[str,Any]|None=None)->None:
        with self.connection() as c: self._queue(c,guild_id,config_id,action,payload or {})



    def set_discord_message(self,config_id:int,message_id:int,status:str="active",error:str|None=None)->None:
        with self.connection() as c: c.execute("UPDATE reaction_role_messages_v2 SET message_id=%s,status=%s,last_error=%s,updated_at=%s WHERE id=%s",(message_id,status,error,int(time.time()),config_id))

    def set_delivery_status(self,config_id:int,status:str,error:str|None=None)->None:
        with self.connection() as c:
            c.execute("UPDATE reaction_role_messages_v2 SET status=%s,last_error=%s,updated_at=%s WHERE id=%s",(status,error[:500] if error else None,int(time.time()),config_id))

    def move_message(self,guild_id:int,config_id:int,channel_id:int,message_id:int,source:str,expected_revision:int,actor_id:int|None=None)->dict[str,Any]:
        with self.connection() as c:
            row=c.execute("SELECT revision,channel_id,message_id,source FROM reaction_role_messages_v2 WHERE guild_id=%s AND id=%s FOR UPDATE",(guild_id,config_id)).fetchone()
            if not row:raise KeyError(config_id)
            if int(row["revision"])!=expected_revision:raise RuntimeError("revision_conflict")
            c.execute("UPDATE reaction_role_messages_v2 SET channel_id=%s,message_id=%s,source=%s,status='active',last_error=NULL,revision=revision+1,updated_at=%s WHERE id=%s",(channel_id,message_id,source,int(time.time()),config_id))
            if row['source'] == 'bot' and row['message_id'] and (row['channel_id'], row['message_id']) != (channel_id, message_id):
                self._queue(c, guild_id, None, 'delete', {'channel_id': row['channel_id'], 'message_id': row['message_id'], 'source': 'bot'})
        self.audit(guild_id,config_id,"message_moved","success",actor_id=actor_id,details={"channel_id":channel_id,"message_id":message_id})
        return self.message(guild_id,config_id) or {}



    def audit(self,guild_id:int,config_id:int|None,event_type:str,result:str,*,user_id:int|None=None,actor_id:int|None=None,emoji_key:str|None=None,role_id:int|None=None,reason:str|None=None,details:dict[str,Any]|None=None)->int:
        now=int(time.time())
        with self.connection() as c: cursor=c.execute('INSERT INTO reaction_role_events(guild_id,message_config_id,user_id,actor_id,emoji_key,role_id,event_type,result,reason,details_json,created_at,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',(guild_id,config_id,user_id,actor_id,emoji_key,role_id,event_type,result,reason,json.dumps(details or {},ensure_ascii=False),now,now+90*86400)); inserted = cursor.fetchone()
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
