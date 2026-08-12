"""SQLite-backed storage shared by the bot and dashboard."""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class GuildStorage:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def _connection(self):
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
        with self._connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    management_channel_id INTEGER,
                    welcome_channel_id INTEGER,
                    default_role_id INTEGER
                );
                CREATE TABLE IF NOT EXISTS guild_users (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    xp INTEGER NOT NULL DEFAULT 0 CHECK (xp >= 0),
                    warn INTEGER NOT NULL DEFAULT 0 CHECK (warn >= 0),
                    PRIMARY KEY (guild_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS guild_voice_users (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    xp INTEGER NOT NULL DEFAULT 0 CHECK (xp >= 0),
                    PRIMARY KEY (guild_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS app_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dashboard_sessions (
                    session_id TEXT PRIMARY KEY,
                    access_token TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_states (
                    state TEXT PRIMARY KEY,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS guild_modules (
                    guild_id INTEGER NOT NULL,
                    module_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                    settings_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY (guild_id, module_id)
                );
                CREATE TABLE IF NOT EXISTS moderation_cases (id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, moderator_id INTEGER, action TEXT NOT NULL, reason TEXT, expires_at INTEGER, dm_sent INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS safe_browsing_cache (url_hash TEXT PRIMARY KEY, unsafe INTEGER NOT NULL, expires_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS reaction_role_panels (message_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, role_ids_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS temporary_voice_channels (channel_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, owner_id INTEGER NOT NULL, created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS support_tickets (channel_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, opener_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'open', created_at INTEGER NOT NULL, closed_at INTEGER, closed_by INTEGER, transcript_json TEXT);
                CREATE TABLE IF NOT EXISTS polls (message_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, creator_id INTEGER NOT NULL, question TEXT NOT NULL, options_json TEXT NOT NULL, image_url TEXT, closes_at INTEGER, status TEXT NOT NULL DEFAULT 'open', created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS poll_votes (message_id INTEGER NOT NULL, user_id INTEGER NOT NULL, option_index INTEGER NOT NULL, created_at INTEGER NOT NULL, PRIMARY KEY (message_id,user_id), FOREIGN KEY(message_id) REFERENCES polls(message_id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS trust_events (id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, category TEXT NOT NULL, weight INTEGER NOT NULL, reason TEXT, created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS social_subscriptions (id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, provider TEXT NOT NULL, account_id TEXT NOT NULL, account_name TEXT NOT NULL, channel_id INTEGER NOT NULL, role_id INTEGER, template TEXT NOT NULL DEFAULT '', events_json TEXT NOT NULL DEFAULT '[]', enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)), created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, UNIQUE(guild_id, provider, account_id));
                CREATE TABLE IF NOT EXISTS social_connections (id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, provider TEXT NOT NULL, account_id TEXT NOT NULL, account_name TEXT NOT NULL, access_token_encrypted TEXT NOT NULL, refresh_token_encrypted TEXT, expires_at INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, UNIQUE(guild_id, provider, account_id));
                CREATE TABLE IF NOT EXISTS social_oauth_states (state TEXT PRIMARY KEY, guild_id INTEGER NOT NULL, provider TEXT NOT NULL, expires_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS social_events (id INTEGER PRIMARY KEY, provider TEXT NOT NULL, event_key TEXT NOT NULL UNIQUE, account_id TEXT NOT NULL, payload_json TEXT NOT NULL, received_at INTEGER NOT NULL, processed_at INTEGER);
                CREATE TABLE IF NOT EXISTS social_deliveries (id INTEGER PRIMARY KEY, subscription_id INTEGER NOT NULL, event_key TEXT NOT NULL, discord_channel_id INTEGER NOT NULL, discord_message_id INTEGER, state TEXT NOT NULL DEFAULT 'sent', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, UNIQUE(subscription_id, event_key));
                CREATE TABLE IF NOT EXISTS social_live_messages (subscription_id INTEGER NOT NULL, provider TEXT NOT NULL, account_id TEXT NOT NULL, discord_channel_id INTEGER NOT NULL, discord_message_id INTEGER NOT NULL, PRIMARY KEY(subscription_id, provider, account_id));
            """)
            # Split the original all-in-one social card without dropping any
            # existing subscription or its enabled state.
            for row in connection.execute("SELECT DISTINCT guild_id, provider FROM social_subscriptions").fetchall():
                module_id = f"{row['provider']}_updates"
                connection.execute("INSERT OR IGNORE INTO guild_modules(guild_id,module_id,enabled,settings_json) VALUES(?,?,1,'{}')", (row["guild_id"], module_id))
            poll_columns = {row["name"] for row in connection.execute("PRAGMA table_info(polls)").fetchall()}
            if poll_columns and "image_url" not in poll_columns:
                connection.execute("ALTER TABLE polls ADD COLUMN image_url TEXT")

    def get_settings(self, guild_id: int) -> dict[str, int | None]:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)).fetchone()
        keys = ("management_channel_id", "welcome_channel_id", "default_role_id")
        return {key: row[key] if row else None for key in keys}

    def update_settings(self, guild_id: int, **settings: int | None) -> None:
        allowed = {"management_channel_id", "welcome_channel_id", "default_role_id"}
        if set(settings) - allowed:
            raise ValueError("Unknown guild setting")
        current = self.get_settings(guild_id)
        current.update(settings)
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO guild_settings (guild_id, management_channel_id, welcome_channel_id, default_role_id)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(guild_id) DO UPDATE SET
                     management_channel_id = excluded.management_channel_id,
                     welcome_channel_id = excluded.welcome_channel_id,
                     default_role_id = excluded.default_role_id""",
                (guild_id, current["management_channel_id"], current["welcome_channel_id"], current["default_role_id"]),
            )

    def get_module(self, guild_id: int, module_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute("SELECT enabled, settings_json FROM guild_modules WHERE guild_id = ? AND module_id = ?", (guild_id, module_id)).fetchone()
        if row:
            settings = json.loads(row["settings_json"])
            if module_id == "welcome":
                settings = self._welcome_settings(settings)
            elif module_id == "audit_log":
                settings = self._audit_log_settings(settings, preserve_legacy_message=True)
            elif module_id == "leveling":
                settings = self._leveling_settings(settings, self.get_settings(guild_id))
            return {"enabled": bool(row["enabled"]), "settings": settings}
        legacy = self.get_settings(guild_id)
        defaults = {"welcome": self._welcome_settings({"welcome_channel_id": legacy["welcome_channel_id"]}), "leveling": self._leveling_settings({}, legacy), "autorole": {"default_role_id": legacy["default_role_id"]}, "audit_log": self._audit_log_settings({"management_channel_id": legacy["management_channel_id"]})}.get(module_id, {})
        return {"enabled": False, "settings": defaults}

    @staticmethod
    def _welcome_settings(settings: dict[str, Any]) -> dict[str, Any]:
        """Normalize legacy welcome settings without silently enabling messages."""
        defaults = {
            "welcome_enabled": False,
            "welcome_channel_id": None,
            "welcome_format": "text",
            "welcome_content": "",
            "leave_enabled": False,
            "leave_channel_id": None,
            "leave_format": "text",
            "leave_content": "",
        }
        defaults.update(settings)
        # Old releases only had a channel. It remains a selectable candidate;
        # no old message text means the new feature stays disabled.
        if defaults["welcome_format"] not in {"text", "embed"}:
            defaults["welcome_format"] = "text"
        if defaults["leave_format"] not in {"text", "embed"}:
            defaults["leave_format"] = "text"
        return defaults

    @staticmethod
    def _audit_log_settings(settings: dict[str, Any], *, preserve_legacy_message: bool = False) -> dict[str, Any]:
        """Normalize category toggles while preserving the old message-only log."""
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
        category_keys = ("log_message", "log_voice", "log_channel", "log_member", "log_role", "log_server")
        if preserve_legacy_message and defaults["management_channel_id"] and not any(key in settings for key in category_keys):
            defaults["log_message"] = True
        return defaults

    @staticmethod
    def _leveling_settings(settings: dict[str, Any], legacy: dict[str, int | None]) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "text_notification_channel_id": legacy["management_channel_id"],
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

    def set_module(self, guild_id: int, module_id: str, *, enabled: bool, settings: dict[str, Any] | None = None) -> None:
        current = self.get_module(guild_id, module_id)
        values = current["settings"] if settings is None else settings
        with self._connection() as connection:
            connection.execute("""INSERT INTO guild_modules (guild_id, module_id, enabled, settings_json) VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, module_id) DO UPDATE SET enabled = excluded.enabled, settings_json = excluded.settings_json""", (guild_id, module_id, int(enabled), json.dumps(values)))

    def module_enabled(self, guild_id: int, module_id: str) -> bool:
        return self.get_module(guild_id, module_id)["enabled"]

    def social_subscriptions(self, guild_id: int, provider: str | None = None) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM social_subscriptions WHERE guild_id=?", [guild_id]
        if provider:
            query += " AND provider=?"
            params.append(provider)
        query += " ORDER BY provider, account_name"
        with self._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [{**dict(row), "events": json.loads(row["events_json"])} for row in rows]

    def social_subscription(self, subscription_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM social_subscriptions WHERE id=?", (subscription_id,)).fetchone()
        return {**dict(row), "events": json.loads(row["events_json"])} if row else None

    def matching_social_subscriptions(self, provider: str, account_id: str, event_type: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM social_subscriptions WHERE provider=? AND account_id=? AND enabled=1", (provider, account_id)).fetchall()
        return [{**dict(row), "events": json.loads(row["events_json"])} for row in rows if event_type in json.loads(row["events_json"])]

    def save_social_subscription(self, guild_id: int, provider: str, account_id: str, account_name: str, channel_id: int, role_id: int | None, template: str, events: list[str], enabled: bool = True, subscription_id: int | None = None) -> int:
        if provider not in {"youtube", "twitch", "tiktok", "x", "instagram"} or len(events) == 0 or len(template) > 1000:
            raise ValueError("Invalid social subscription")
        now = int(time.time())
        with self._connection() as connection:
            if subscription_id is None:
                count = connection.execute("SELECT COUNT(*) FROM social_subscriptions WHERE guild_id=? AND provider=?", (guild_id, provider)).fetchone()[0]
                if count >= 10:
                    raise ValueError("Provider account limit reached")
                cursor = connection.execute("INSERT INTO social_subscriptions(guild_id,provider,account_id,account_name,channel_id,role_id,template,events_json,enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (guild_id, provider, account_id, account_name, channel_id, role_id, template, json.dumps(events), int(enabled), now, now))
                return int(cursor.lastrowid)
            connection.execute("UPDATE social_subscriptions SET provider=?,account_id=?,account_name=?,channel_id=?,role_id=?,template=?,events_json=?,enabled=?,updated_at=? WHERE id=? AND guild_id=?", (provider, account_id, account_name, channel_id, role_id, template, json.dumps(events), int(enabled), now, subscription_id, guild_id))
            return subscription_id

    def delete_social_subscription(self, guild_id: int, subscription_id: int) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM social_subscriptions WHERE guild_id=? AND id=?", (guild_id, subscription_id))

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

    def enqueue_social_event(self, provider: str, event_key: str, account_id: str, payload: dict[str, Any]) -> bool:
        with self._connection() as connection:
            cursor = connection.execute("INSERT OR IGNORE INTO social_events(provider,event_key,account_id,payload_json,received_at) VALUES(?,?,?,?,?)", (provider, event_key, account_id, json.dumps(payload), int(time.time())))
        return cursor.rowcount == 1

    def pending_social_events(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM social_events WHERE processed_at IS NULL ORDER BY id LIMIT 100").fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def mark_social_event_processed(self, event_id: int) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE social_events SET processed_at=? WHERE id=?", (int(time.time()), event_id))

    def record_social_delivery(self, subscription_id: int, event_key: str, channel_id: int, message_id: int | None, state: str = "sent") -> bool:
        now = int(time.time())
        with self._connection() as connection:
            cursor = connection.execute("INSERT OR IGNORE INTO social_deliveries(subscription_id,event_key,discord_channel_id,discord_message_id,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (subscription_id, event_key, channel_id, message_id, state, now, now))
        return cursor.rowcount == 1

    def update_social_delivery(self, subscription_id: int, event_key: str, message_id: int, state: str = "sent") -> None:
        with self._connection() as connection:
            connection.execute("UPDATE social_deliveries SET discord_message_id=?,state=?,updated_at=? WHERE subscription_id=? AND event_key=?", (message_id, state, int(time.time()), subscription_id, event_key))

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

    def add_case(self, guild_id: int, user_id: int, action: str, reason: str | None, moderator_id: int | None = None, expires_at: int | None = None, dm_sent: bool = False) -> None:
        weights = {"warn": -10, "timeout": -20, "kick": -30, "ban": -40, "spam": -15, "anti_spam": -15, "chat_filter": -10, "phishing": -20}
        now = int(time.time())
        with self._connection() as c:
            c.execute("INSERT INTO moderation_cases (guild_id,user_id,moderator_id,action,reason,expires_at,dm_sent,created_at) VALUES (?,?,?,?,?,?,?,?)", (guild_id,user_id,moderator_id,action,reason,expires_at,int(dm_sent),now))
            trust_enabled = c.execute("SELECT enabled FROM guild_modules WHERE guild_id=? AND module_id='trust_score'", (guild_id,)).fetchone()
            if action in weights and trust_enabled and trust_enabled["enabled"]:
                c.execute("INSERT INTO trust_events (guild_id,user_id,category,weight,reason,created_at) VALUES (?,?,?,?,?,?)", (guild_id, user_id, action, weights[action], reason, now))

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

    def save_reaction_role_panel(self, message_id: int, guild_id: int, role_ids: list[int]) -> None:
        if not 1 <= len(role_ids) <= 25 or len(set(role_ids)) != len(role_ids):
            raise ValueError("Reaction role panels require 1 to 25 unique roles")
        with self._connection() as c:
            c.execute("INSERT OR REPLACE INTO reaction_role_panels (message_id,guild_id,role_ids_json) VALUES (?,?,?)", (message_id, guild_id, json.dumps(role_ids)))

    def reaction_role_panel(self, message_id: int) -> dict[str, Any] | None:
        with self._connection() as c:
            row = c.execute("SELECT guild_id, role_ids_json FROM reaction_role_panels WHERE message_id=?", (message_id,)).fetchone()
        return {"guild_id": row["guild_id"], "role_ids": json.loads(row["role_ids_json"])} if row else None

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

    def create_ticket(self, channel_id: int, guild_id: int, opener_id: int) -> None:
        with self._connection() as c:
            c.execute("INSERT INTO support_tickets (channel_id,guild_id,opener_id,status,created_at) VALUES (?,?,?,'open',?)", (channel_id, guild_id, opener_id, int(time.time())))

    def ticket(self, channel_id: int) -> dict[str, Any] | None:
        with self._connection() as c:
            row = c.execute("SELECT * FROM support_tickets WHERE channel_id=?", (channel_id,)).fetchone()
        return dict(row) if row else None

    def close_ticket(self, channel_id: int, closed_by: int, transcript: list[dict[str, Any]]) -> None:
        with self._connection() as c:
            c.execute("UPDATE support_tickets SET status='closed',closed_at=?,closed_by=?,transcript_json=? WHERE channel_id=? AND status='open'", (int(time.time()), closed_by, json.dumps(transcript, ensure_ascii=False), channel_id))

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

    # Compatibility helpers for small existing consumers.
    def get(self, guild_id: int, key: str, default: Any = None) -> Any:
        return self.get_settings(guild_id).get(key, default)

    def set(self, guild_id: int, key: str, value: Any) -> None:
        self.update_settings(guild_id, **{key: value})

    def get_user(self, guild_id: int, user_id: int) -> dict[str, int]:
        with self._connection() as connection:
            row = connection.execute("SELECT xp, warn FROM guild_users WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)).fetchone()
        return {"xp": row["xp"], "warn": row["warn"]} if row else {"xp": 0, "warn": 0}

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

    def add_warning(self, guild_id: int, user_id: int) -> int:
        with self._connection() as connection:
            connection.execute("INSERT INTO guild_users (guild_id, user_id, warn) VALUES (?, ?, 1) ON CONFLICT(guild_id, user_id) DO UPDATE SET warn = warn + 1", (guild_id, user_id))
        return self.get_user(guild_id, user_id)["warn"]

    def leaderboard(self, guild_id: int, limit: int = 5) -> list[dict[str, int]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT user_id, xp FROM guild_users WHERE guild_id = ? ORDER BY xp DESC, user_id ASC LIMIT ?", (guild_id, limit)).fetchall()
        return [{"user_id": row["user_id"], "xp": row["xp"]} for row in rows]

    def migrated(self) -> bool:
        with self._connection() as connection:
            return connection.execute("SELECT 1 FROM app_metadata WHERE key = 'json_migration_v1'").fetchone() is not None

    def create_dashboard_session(self, session_id: str, access_token: str, expires_in: int) -> None:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("DELETE FROM dashboard_sessions WHERE expires_at <= ?", (now,))
            connection.execute("INSERT INTO dashboard_sessions (session_id, access_token, expires_at) VALUES (?, ?, ?)", (session_id, access_token, now + expires_in))

    def dashboard_session_token(self, session_id: str) -> str | None:
        with self._connection() as connection:
            row = connection.execute("SELECT access_token FROM dashboard_sessions WHERE session_id = ? AND expires_at > ?", (session_id, int(time.time()))).fetchone()
        return row["access_token"] if row else None

    def delete_dashboard_session(self, session_id: str) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM dashboard_sessions WHERE session_id = ?", (session_id,))

    def create_oauth_state(self, state: str, expires_in: int = 600) -> None:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("DELETE FROM oauth_states WHERE expires_at <= ?", (now,))
            connection.execute("INSERT INTO oauth_states (state, expires_at) VALUES (?, ?)", (state, now + expires_in))

    def consume_oauth_state(self, state: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM oauth_states WHERE state = ? AND expires_at > ?", (state, int(time.time())))
        return cursor.rowcount == 1

    def migrate_json(self, data_dir: Path) -> int:
        if self.migrated():
            return 0
        migrated = 0
        for path in data_dir.glob("*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                guild_id = int(path.stem)
            except (ValueError, json.JSONDecodeError):
                continue
            settings = {key: raw.get(key) for key in ("management_channel_id", "welcome_channel_id", "default_role_id") if key in raw}
            if settings:
                self.update_settings(guild_id, **settings)
            for user_id, user in raw.get("users", raw).items():
                if not isinstance(user, dict) or not str(user_id).isdigit():
                    continue
                with self._connection() as connection:
                    connection.execute("INSERT OR REPLACE INTO guild_users (guild_id, user_id, xp, warn) VALUES (?, ?, ?, ?)", (guild_id, int(user_id), int(user.get("xp", 0)), int(user.get("warn", 0))))
            migrated += 1
        with self._connection() as connection:
            connection.execute("INSERT INTO app_metadata (key, value) VALUES ('json_migration_v1', 'complete')")
        return migrated
