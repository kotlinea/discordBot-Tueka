"""SQLite repository for Reaction Roles."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class ReactionRoleRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS reaction_role_settings (
                guild_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
                log_channel_id INTEGER, denial_dm INTEGER NOT NULL DEFAULT 1 CHECK(denial_dm IN (0,1)),
                denial_dm_cooldown_seconds INTEGER NOT NULL DEFAULT 300, audit_retention_days INTEGER NOT NULL DEFAULT 90,
                revision INTEGER NOT NULL DEFAULT 1, updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reaction_role_link_groups (
                id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, name TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reaction_role_messages_v2 (
                id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, message_id INTEGER,
                name TEXT NOT NULL, source TEXT NOT NULL CHECK(source IN ('bot','external')),
                behavior_type TEXT NOT NULL, locked INTEGER NOT NULL DEFAULT 0 CHECK(locked IN (0,1)),
                access_policy TEXT NOT NULL DEFAULT 'blacklist' CHECK(access_policy IN ('whitelist','blacklist')),
                selection_limit INTEGER, temp_duration_seconds INTEGER, self_destruct_at INTEGER,
                embed_json TEXT NOT NULL DEFAULT '{}', link_group_id INTEGER, enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
                status TEXT NOT NULL DEFAULT 'pending', last_error TEXT, revision INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                UNIQUE(guild_id,message_id), FOREIGN KEY(link_group_id) REFERENCES reaction_role_link_groups(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_rr_messages_guild ON reaction_role_messages_v2(guild_id,enabled,id);
            CREATE TABLE IF NOT EXISTS reaction_role_mappings_v2 (
                id INTEGER PRIMARY KEY, message_config_id INTEGER NOT NULL, emoji_key TEXT NOT NULL, emoji_display TEXT NOT NULL,
                emoji_id INTEGER, emoji_name TEXT, animated INTEGER NOT NULL DEFAULT 0, role_id INTEGER NOT NULL,
                max_members INTEGER, position INTEGER NOT NULL, UNIQUE(message_config_id,emoji_key),
                UNIQUE(message_config_id,role_id), FOREIGN KEY(message_config_id) REFERENCES reaction_role_messages_v2(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS reaction_role_access_roles (
                message_config_id INTEGER NOT NULL, role_id INTEGER NOT NULL, policy TEXT NOT NULL CHECK(policy IN ('whitelist','blacklist')),
                PRIMARY KEY(message_config_id,role_id), FOREIGN KEY(message_config_id) REFERENCES reaction_role_messages_v2(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS reaction_role_binding_receipts (
                message_config_id INTEGER NOT NULL, user_id INTEGER NOT NULL, mapping_id INTEGER NOT NULL, created_at INTEGER NOT NULL,
                PRIMARY KEY(message_config_id,user_id), FOREIGN KEY(message_config_id) REFERENCES reaction_role_messages_v2(id) ON DELETE CASCADE,
                FOREIGN KEY(mapping_id) REFERENCES reaction_role_mappings_v2(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS reaction_role_assignments (
                message_config_id INTEGER NOT NULL, mapping_id INTEGER NOT NULL, user_id INTEGER NOT NULL, role_id INTEGER NOT NULL,
                state TEXT NOT NULL DEFAULT 'active', expires_at INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                PRIMARY KEY(message_config_id,mapping_id,user_id), FOREIGN KEY(message_config_id) REFERENCES reaction_role_messages_v2(id) ON DELETE CASCADE,
                FOREIGN KEY(mapping_id) REFERENCES reaction_role_mappings_v2(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_rr_assignments_due ON reaction_role_assignments(state,expires_at);
            CREATE TABLE IF NOT EXISTS reaction_role_schedules (
                id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, message_config_id INTEGER, mapping_id INTEGER, user_id INTEGER,
                kind TEXT NOT NULL, due_at INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'pending', lease_owner TEXT, lease_until INTEGER,
                attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, created_at INTEGER NOT NULL,
                UNIQUE(kind,message_config_id,mapping_id,user_id,due_at)
            );
            CREATE INDEX IF NOT EXISTS idx_rr_schedules_due ON reaction_role_schedules(state,due_at,lease_until);
            CREATE TABLE IF NOT EXISTS reaction_role_outbox (
                id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, message_config_id INTEGER, action TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'pending', lease_owner TEXT, lease_until INTEGER,
                attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at INTEGER NOT NULL DEFAULT 0, last_error TEXT, created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_rr_outbox_due ON reaction_role_outbox(state,next_attempt_at,lease_until);
            CREATE TABLE IF NOT EXISTS reaction_role_events (
                id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, message_config_id INTEGER, user_id INTEGER, actor_id INTEGER,
                emoji_key TEXT, role_id INTEGER, event_type TEXT NOT NULL, result TEXT NOT NULL, reason TEXT,
                details_json TEXT NOT NULL DEFAULT '{}', created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_rr_events_guild ON reaction_role_events(guild_id,created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_rr_events_expiry ON reaction_role_events(expires_at);
            CREATE TABLE IF NOT EXISTS reaction_role_recovery (
                guild_id INTEGER NOT NULL, deleted_message_id INTEGER NOT NULL, snapshot_json TEXT NOT NULL,
                created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, PRIMARY KEY(guild_id,deleted_message_id)
            );
            """)
            columns={row["name"] for row in c.execute("PRAGMA table_info(reaction_role_messages_v2)").fetchall()}
            if "access_policy" not in columns:
                c.execute("ALTER TABLE reaction_role_messages_v2 ADD COLUMN access_policy TEXT NOT NULL DEFAULT 'blacklist'")

    def settings(self, guild_id: int) -> dict[str, Any]:
        with self.connection() as c:
            row = c.execute("SELECT * FROM reaction_role_settings WHERE guild_id=?", (guild_id,)).fetchone()
            if not row:
                has_legacy = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='guild_modules'").fetchone()
                legacy = c.execute("SELECT enabled FROM guild_modules WHERE guild_id=? AND module_id='reaction_roles'",(guild_id,)).fetchone() if has_legacy else None
                if legacy:
                    now=int(time.time());c.execute("INSERT INTO reaction_role_settings(guild_id,enabled,updated_at) VALUES(?,?,?)",(guild_id,int(legacy["enabled"]),now));row=c.execute("SELECT * FROM reaction_role_settings WHERE guild_id=?",(guild_id,)).fetchone()
        return dict(row) if row else {"guild_id": guild_id, "enabled": False, "log_channel_id": None, "denial_dm": True, "denial_dm_cooldown_seconds": 300, "audit_retention_days": 90, "revision": 0}

    def save_settings(self, guild_id: int, value: dict[str, Any], expected_revision: int | None) -> dict[str, Any]:
        now = int(time.time())
        with self.connection() as c:
            row = c.execute("SELECT revision FROM reaction_role_settings WHERE guild_id=?", (guild_id,)).fetchone()
            revision = int(row["revision"]) if row else 0
            if expected_revision is not None and revision != expected_revision:
                raise RuntimeError("revision_conflict")
            c.execute("""INSERT INTO reaction_role_settings(guild_id,enabled,log_channel_id,denial_dm,denial_dm_cooldown_seconds,audit_retention_days,revision,updated_at)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(guild_id) DO UPDATE SET enabled=excluded.enabled,log_channel_id=excluded.log_channel_id,
                denial_dm=excluded.denial_dm,denial_dm_cooldown_seconds=excluded.denial_dm_cooldown_seconds,
                audit_retention_days=excluded.audit_retention_days,revision=excluded.revision,updated_at=excluded.updated_at""",
                (guild_id, int(bool(value.get("enabled"))), value.get("log_channel_id"), int(bool(value.get("denial_dm", True))),
                 max(30, min(int(value.get("denial_dm_cooldown_seconds", 300)), 86400)), 90, revision + 1, now))
        return self.settings(guild_id)

    @staticmethod
    def _decode_message(row: sqlite3.Row, mappings: list[sqlite3.Row], access: list[sqlite3.Row]) -> dict[str, Any]:
        value = dict(row)
        value.update({"locked": bool(value["locked"]), "enabled": bool(value["enabled"]), "embed": json.loads(value.pop("embed_json"))})
        value["mappings"] = [{"id": item["id"], "emoji": item["emoji_display"], "emoji_key": item["emoji_key"], "emoji_id": item["emoji_id"],
            "emoji_name": item["emoji_name"], "animated": bool(item["animated"]), "role_id": item["role_id"], "max_members": item["max_members"], "position": item["position"]} for item in mappings]
        value["whitelist_role_ids"] = [item["role_id"] for item in access if item["policy"] == "whitelist"]
        value["blacklist_role_ids"] = [item["role_id"] for item in access if item["policy"] == "blacklist"]
        if value["whitelist_role_ids"] and not value["blacklist_role_ids"]:
            value["access_policy"] = "whitelist"
        return value

    def message(self, guild_id: int, config_id: int) -> dict[str, Any] | None:
        with self.connection() as c:
            row = c.execute("SELECT * FROM reaction_role_messages_v2 WHERE guild_id=? AND id=?", (guild_id, config_id)).fetchone()
            if not row: return None
            mappings = c.execute("SELECT * FROM reaction_role_mappings_v2 WHERE message_config_id=? ORDER BY position,id", (config_id,)).fetchall()
            access = c.execute("SELECT * FROM reaction_role_access_roles WHERE message_config_id=?", (config_id,)).fetchall()
        return self._decode_message(row, mappings, access)

    def message_by_discord_id(self, guild_id: int, message_id: int) -> dict[str, Any] | None:
        with self.connection() as c:
            row = c.execute("SELECT id FROM reaction_role_messages_v2 WHERE guild_id=? AND message_id=?", (guild_id, message_id)).fetchone()
        return self.message(guild_id, int(row["id"])) if row else None

    def messages(self, guild_id: int, *, include_disabled: bool = True) -> list[dict[str, Any]]:
        query = "SELECT id FROM reaction_role_messages_v2 WHERE guild_id=?" + ("" if include_disabled else " AND enabled=1") + " ORDER BY id DESC"
        with self.connection() as c: ids = [int(row["id"]) for row in c.execute(query, (guild_id,)).fetchall()]
        return [item for config_id in ids if (item := self.message(guild_id, config_id))]

    def _replace_children(self, c: sqlite3.Connection, config_id: int, value: dict[str, Any]) -> None:
        existing = {(row["emoji_key"], int(row["role_id"])): int(row["id"]) for row in c.execute(
            "SELECT id,emoji_key,role_id FROM reaction_role_mappings_v2 WHERE message_config_id=?", (config_id,)).fetchall()}
        incoming = {(item["key"], int(item["role_id"])) for item in value["mappings"]}
        removed = [mapping_id for pair, mapping_id in existing.items() if pair not in incoming]
        if removed:
            c.execute(f"DELETE FROM reaction_role_mappings_v2 WHERE id IN ({','.join('?' for _ in removed)})", removed)
        for item in value["mappings"]:
            pair = (item["key"], int(item["role_id"]))
            if pair in existing:
                c.execute("UPDATE reaction_role_mappings_v2 SET emoji_display=?,emoji_id=?,emoji_name=?,animated=?,max_members=?,position=? WHERE id=?",
                    (item["display"],item["emoji_id"],item["emoji_name"],int(item["animated"]),item["max_members"],item["position"],existing[pair]))
            else:
                c.execute("""INSERT INTO reaction_role_mappings_v2(message_config_id,emoji_key,emoji_display,emoji_id,emoji_name,animated,role_id,max_members,position)
                    VALUES(?,?,?,?,?,?,?,?,?)""", (config_id,item["key"],item["display"],item["emoji_id"],item["emoji_name"],int(item["animated"]),item["role_id"],item["max_members"],item["position"]))
        c.execute("DELETE FROM reaction_role_access_roles WHERE message_config_id=?", (config_id,))
        for policy, key in (("whitelist", "whitelist_role_ids"), ("blacklist", "blacklist_role_ids")):
            c.executemany("INSERT INTO reaction_role_access_roles(message_config_id,role_id,policy) VALUES(?,?,?)", [(config_id, role_id, policy) for role_id in value[key]])

    def create_message(self, guild_id: int, value: dict[str, Any], actor_id: int | None = None) -> dict[str, Any]:
        now = int(time.time())
        with self.connection() as c:
            cursor = c.execute("""INSERT INTO reaction_role_messages_v2(guild_id,channel_id,message_id,name,source,behavior_type,locked,access_policy,selection_limit,temp_duration_seconds,self_destruct_at,embed_json,link_group_id,enabled,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (guild_id,value["channel_id"],value["message_id"],value["name"],value["source"],value["behavior_type"],int(value["locked"]),value["access_policy"],value["selection_limit"],value["temp_duration_seconds"],value["self_destruct_at"],json.dumps(value["embed"],ensure_ascii=False),value["link_group_id"],int(value["enabled"]),"active" if value["message_id"] else "pending",now,now))
            config_id = int(cursor.lastrowid); self._replace_children(c, config_id, value)
            if value["source"] == "bot": self._queue(c, guild_id, config_id, "publish", {})
            if value["self_destruct_at"]: self._schedule(c,guild_id,config_id,None,None,"self_destruct",value["self_destruct_at"])
        self.audit(guild_id, config_id, "config_created", "success", actor_id=actor_id)
        return self.message(guild_id, config_id) or {}

    def update_message(self, guild_id: int, config_id: int, value: dict[str, Any], expected_revision: int, actor_id: int | None = None) -> dict[str, Any]:
        now = int(time.time())
        with self.connection() as c:
            row = c.execute("SELECT revision,source FROM reaction_role_messages_v2 WHERE guild_id=? AND id=?", (guild_id,config_id)).fetchone()
            if not row: raise KeyError(config_id)
            if int(row["revision"]) != expected_revision: raise RuntimeError("revision_conflict")
            if row["source"] == "external" and value["source"] != "external": raise ValueError("source_immutable")
            c.execute("""UPDATE reaction_role_messages_v2 SET channel_id=?,message_id=?,name=?,behavior_type=?,locked=?,access_policy=?,selection_limit=?,temp_duration_seconds=?,self_destruct_at=?,embed_json=?,link_group_id=?,enabled=?,status='pending',last_error=NULL,revision=revision+1,updated_at=? WHERE id=?""",
                (value["channel_id"],value["message_id"],value["name"],value["behavior_type"],int(value["locked"]),value["access_policy"],value["selection_limit"],value["temp_duration_seconds"],value["self_destruct_at"],json.dumps(value["embed"],ensure_ascii=False),value["link_group_id"],int(value["enabled"]),now,config_id))
            self._replace_children(c, config_id, value); self._queue(c,guild_id,config_id,"sync",{})
            c.execute("DELETE FROM reaction_role_schedules WHERE message_config_id=? AND kind='self_destruct' AND state='pending'",(config_id,))
            if value["self_destruct_at"]:self._schedule(c,guild_id,config_id,None,None,"self_destruct",value["self_destruct_at"])
        self.audit(guild_id,config_id,"config_updated","success",actor_id=actor_id)
        return self.message(guild_id,config_id) or {}

    def delete_message(self, guild_id: int, config_id: int, *, recoverable: bool, actor_id: int | None = None) -> None:
        item = self.message(guild_id, config_id)
        if not item: return
        now = int(time.time())
        with self.connection() as c:
            if recoverable and item.get("message_id"):
                snapshot = {key:value for key,value in item.items() if key not in {"last_error"}}
                c.execute("INSERT OR REPLACE INTO reaction_role_recovery VALUES(?,?,?,?,?)", (guild_id,item["message_id"],json.dumps(snapshot,ensure_ascii=False),now,now+604800))
            c.execute("DELETE FROM reaction_role_messages_v2 WHERE guild_id=? AND id=?", (guild_id,config_id))
        self.audit(guild_id,None,"message_deleted","success",actor_id=actor_id,details={"message_id":item.get("message_id"),"recoverable":recoverable})

    def recovery(self, guild_id: int, message_id: int) -> dict[str, Any] | None:
        with self.connection() as c:
            row=c.execute("SELECT snapshot_json FROM reaction_role_recovery WHERE guild_id=? AND deleted_message_id=? AND expires_at>?",(guild_id,message_id,int(time.time()))).fetchone()
        return json.loads(row["snapshot_json"]) if row else None

    def consume_recovery(self,guild_id:int,message_id:int)->None:
        with self.connection() as c:c.execute("DELETE FROM reaction_role_recovery WHERE guild_id=? AND deleted_message_id=?",(guild_id,message_id))

    def recoveries(self,guild_id:int)->list[dict[str,Any]]:
        now=int(time.time())
        with self.connection() as c:rows=c.execute("SELECT deleted_message_id,created_at,expires_at FROM reaction_role_recovery WHERE guild_id=? AND expires_at>? ORDER BY created_at DESC",(guild_id,now)).fetchall()
        return [dict(row) for row in rows]

    def create_link_group(self, guild_id: int, name: str, config_ids: list[int]) -> dict[str, Any]:
        if len(set(config_ids)) < 2:
            raise ValueError("link_members")
        now=int(time.time())
        with self.connection() as c:
            rows=c.execute(f"SELECT id,behavior_type,link_group_id FROM reaction_role_messages_v2 WHERE guild_id=? AND id IN ({','.join('?' for _ in config_ids)})",(guild_id,*config_ids)).fetchall()
            if len(rows)<2 or len(rows)!=len(set(config_ids)): raise ValueError("link_members")
            if any(row["behavior_type"] not in {"normal","unique","temp"} or row["link_group_id"] is not None for row in rows): raise ValueError("link_conflict")
            cursor=c.execute("INSERT INTO reaction_role_link_groups(guild_id,name,created_at,updated_at) VALUES(?,?,?,?)",(guild_id,name[:100] or "Link Group",now,now)); group_id=int(cursor.lastrowid)
            c.execute(f"UPDATE reaction_role_messages_v2 SET link_group_id=?,revision=revision+1,updated_at=? WHERE guild_id=? AND id IN ({','.join('?' for _ in config_ids)})",(group_id,now,guild_id,*config_ids))
        return self.link_group(guild_id,group_id) or {}

    def link_group(self,guild_id:int,group_id:int)->dict[str,Any]|None:
        with self.connection() as c:
            row=c.execute("SELECT * FROM reaction_role_link_groups WHERE guild_id=? AND id=?",(guild_id,group_id)).fetchone()
            members=c.execute("SELECT id FROM reaction_role_messages_v2 WHERE guild_id=? AND link_group_id=? ORDER BY id",(guild_id,group_id)).fetchall() if row else []
        return {**dict(row),"message_ids":[item["id"] for item in members]} if row else None

    def link_groups(self,guild_id:int)->list[dict[str,Any]]:
        with self.connection() as c: ids=[row["id"] for row in c.execute("SELECT id FROM reaction_role_link_groups WHERE guild_id=? ORDER BY id",(guild_id,)).fetchall()]
        return [item for group_id in ids if (item:=self.link_group(guild_id,group_id))]

    def dissolve_link_group(self,guild_id:int,group_id:int)->None:
        with self.connection() as c:
            c.execute("UPDATE reaction_role_messages_v2 SET link_group_id=NULL,revision=revision+1 WHERE guild_id=? AND link_group_id=?",(guild_id,group_id)); c.execute("DELETE FROM reaction_role_link_groups WHERE guild_id=? AND id=?",(guild_id,group_id))

    def assignments(self, user_id: int, *, config_id: int | None = None, link_group_id: int | None = None) -> list[dict[str,Any]]:
        with self.connection() as c:
            if link_group_id is not None:
                rows=c.execute("""SELECT a.* FROM reaction_role_assignments a JOIN reaction_role_messages_v2 m ON m.id=a.message_config_id WHERE a.user_id=? AND a.state='active' AND m.link_group_id=?""",(user_id,link_group_id)).fetchall()
            else: rows=c.execute("SELECT * FROM reaction_role_assignments WHERE user_id=? AND message_config_id=? AND state='active'",(user_id,config_id)).fetchall()
        return [dict(row) for row in rows]

    def binding_receipt(self,config_id:int,user_id:int)->dict[str,Any]|None:
        with self.connection() as c: row=c.execute("SELECT * FROM reaction_role_binding_receipts WHERE message_config_id=? AND user_id=?",(config_id,user_id)).fetchone()
        return dict(row) if row else None

    def reset_binding(self,config_id:int,user_id:int)->bool:
        with self.connection() as c: cursor=c.execute("DELETE FROM reaction_role_binding_receipts WHERE message_config_id=? AND user_id=?",(config_id,user_id))
        return cursor.rowcount>0

    def activate_assignment(self,guild_id:int,config_id:int,mapping_id:int,user_id:int,role_id:int,expires_at:int|None,binding:bool=False)->None:
        now=int(time.time())
        with self.connection() as c:
            c.execute("""INSERT INTO reaction_role_assignments VALUES(?,?,?,?, 'active',?,?,?) ON CONFLICT(message_config_id,mapping_id,user_id) DO UPDATE SET state='active',expires_at=excluded.expires_at,updated_at=excluded.updated_at""",(config_id,mapping_id,user_id,role_id,expires_at,now,now))
            if binding: c.execute("INSERT OR IGNORE INTO reaction_role_binding_receipts VALUES(?,?,?,?)",(config_id,user_id,mapping_id,now))
            if expires_at: self._schedule(c,guild_id,config_id,mapping_id,user_id,"temp_role",expires_at)

    def deactivate_assignment(self,config_id:int,mapping_id:int,user_id:int)->None:
        with self.connection() as c: c.execute("UPDATE reaction_role_assignments SET state='removed',updated_at=? WHERE message_config_id=? AND mapping_id=? AND user_id=?",(int(time.time()),config_id,mapping_id,user_id))

    @staticmethod
    def _schedule(c:sqlite3.Connection,guild_id:int,config_id:int|None,mapping_id:int|None,user_id:int|None,kind:str,due_at:int)->None:
        c.execute("INSERT OR IGNORE INTO reaction_role_schedules(guild_id,message_config_id,mapping_id,user_id,kind,due_at,created_at) VALUES(?,?,?,?,?,?,?)",(guild_id,config_id,mapping_id,user_id,kind,due_at,int(time.time())))

    @staticmethod
    def _queue(c:sqlite3.Connection,guild_id:int,config_id:int|None,action:str,payload:dict[str,Any])->None:
        c.execute("INSERT INTO reaction_role_outbox(guild_id,message_config_id,action,payload_json,created_at) VALUES(?,?,?,?,?)",(guild_id,config_id,action,json.dumps(payload),int(time.time())))

    def queue_action(self,guild_id:int,config_id:int|None,action:str,payload:dict[str,Any]|None=None)->None:
        with self.connection() as c: self._queue(c,guild_id,config_id,action,payload or {})

    def claim_outbox(self,owner:str,limit:int=20)->list[dict[str,Any]]:
        now=int(time.time())
        with self.connection() as c:
            lease_until=now+30
            c.execute("""UPDATE reaction_role_outbox SET lease_owner=?,lease_until=? WHERE id IN (
                SELECT id FROM reaction_role_outbox WHERE state='pending' AND next_attempt_at<=?
                AND (lease_until IS NULL OR lease_until<?) ORDER BY id LIMIT ?)""",(owner,lease_until,now,now,limit))
            rows=c.execute("SELECT * FROM reaction_role_outbox WHERE state='pending' AND lease_owner=? AND lease_until=? ORDER BY id",(owner,lease_until)).fetchall()
        return [{**dict(row),"payload":json.loads(row["payload_json"])} for row in rows]

    def finish_outbox(self,item_id:int,owner:str,error:str|None=None,retry:bool=False)->None:
        with self.connection() as c:
            row=c.execute("SELECT attempts FROM reaction_role_outbox WHERE id=? AND lease_owner=?",(item_id,owner)).fetchone()
            attempts=int(row["attempts"])+1 if row else 1
            if error and retry: c.execute("UPDATE reaction_role_outbox SET attempts=?,last_error=?,lease_owner=NULL,lease_until=NULL,next_attempt_at=?,state='pending' WHERE id=? AND lease_owner=?",(attempts,error[:500],int(time.time())+min(300,2**min(8,attempts)),item_id,owner))
            else: c.execute("UPDATE reaction_role_outbox SET attempts=attempts+1,last_error=?,lease_owner=NULL,lease_until=NULL,state=? WHERE id=? AND lease_owner=?",(error[:500] if error else None,"failed" if error else "done",item_id,owner))

    def set_discord_message(self,config_id:int,message_id:int,status:str="active",error:str|None=None)->None:
        with self.connection() as c: c.execute("UPDATE reaction_role_messages_v2 SET message_id=?,status=?,last_error=?,updated_at=? WHERE id=?",(message_id,status,error,int(time.time()),config_id))

    def set_delivery_status(self,config_id:int,status:str,error:str|None=None)->None:
        with self.connection() as c:
            c.execute("UPDATE reaction_role_messages_v2 SET status=?,last_error=?,updated_at=? WHERE id=?",(status,error[:500] if error else None,int(time.time()),config_id))

    def move_message(self,guild_id:int,config_id:int,channel_id:int,message_id:int,source:str,expected_revision:int,actor_id:int|None=None)->dict[str,Any]:
        with self.connection() as c:
            row=c.execute("SELECT revision FROM reaction_role_messages_v2 WHERE guild_id=? AND id=?",(guild_id,config_id)).fetchone()
            if not row:raise KeyError(config_id)
            if int(row["revision"])!=expected_revision:raise RuntimeError("revision_conflict")
            c.execute("UPDATE reaction_role_messages_v2 SET channel_id=?,message_id=?,source=?,status='active',last_error=NULL,revision=revision+1,updated_at=? WHERE id=?",(channel_id,message_id,source,int(time.time()),config_id))
        self.audit(guild_id,config_id,"message_moved","success",actor_id=actor_id,details={"channel_id":channel_id,"message_id":message_id})
        return self.message(guild_id,config_id) or {}

    def due_schedules(self,owner:str,limit:int=100)->list[dict[str,Any]]:
        now=int(time.time())
        with self.connection() as c:
            rows=c.execute("SELECT * FROM reaction_role_schedules WHERE state='pending' AND due_at<=? AND (lease_until IS NULL OR lease_until<?) ORDER BY due_at LIMIT ?",(now,now,limit)).fetchall(); ids=[row["id"] for row in rows]
            if ids:c.execute(f"UPDATE reaction_role_schedules SET lease_owner=?,lease_until=? WHERE id IN ({','.join('?' for _ in ids)})",(owner,now+60,*ids))
        return [dict(row) for row in rows]

    def finish_schedule(self,schedule_id:int,owner:str,error:str|None=None)->None:
        with self.connection() as c:
            if error:c.execute("UPDATE reaction_role_schedules SET attempts=attempts+1,last_error=?,lease_owner=NULL,lease_until=NULL,due_at=? WHERE id=? AND lease_owner=?",(error[:500],int(time.time())+60,schedule_id,owner))
            else:c.execute("UPDATE reaction_role_schedules SET state='done',lease_owner=NULL,lease_until=NULL,last_error=NULL WHERE id=? AND lease_owner=?",(schedule_id,owner))

    def audit(self,guild_id:int,config_id:int|None,event_type:str,result:str,*,user_id:int|None=None,actor_id:int|None=None,emoji_key:str|None=None,role_id:int|None=None,reason:str|None=None,details:dict[str,Any]|None=None)->int:
        now=int(time.time())
        with self.connection() as c: cursor=c.execute("""INSERT INTO reaction_role_events(guild_id,message_config_id,user_id,actor_id,emoji_key,role_id,event_type,result,reason,details_json,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",(guild_id,config_id,user_id,actor_id,emoji_key,role_id,event_type,result,reason,json.dumps(details or {},ensure_ascii=False),now,now+90*86400))
        return int(cursor.lastrowid)

    def events(self,guild_id:int,limit:int=100)->list[dict[str,Any]]:
        with self.connection() as c: rows=c.execute("SELECT * FROM reaction_role_events WHERE guild_id=? ORDER BY id DESC LIMIT ?",(guild_id,max(1,min(limit,500)))).fetchall()
        return [{**dict(row),"details":json.loads(row["details_json"])} for row in rows]

    def maintain(self)->dict[str,int]:
        now=int(time.time())
        with self.connection() as c:
            events=c.execute("DELETE FROM reaction_role_events WHERE expires_at<=?",(now,)).rowcount
            recovery=c.execute("DELETE FROM reaction_role_recovery WHERE expires_at<=?",(now,)).rowcount
        return {"events":events,"recovery":recovery}
