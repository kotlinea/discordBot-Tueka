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
            """)

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
            return {"enabled": bool(row["enabled"]), "settings": json.loads(row["settings_json"])}
        legacy = self.get_settings(guild_id)
        defaults = {"welcome": {key: legacy[key] for key in ("welcome_channel_id", "default_role_id")}, "audit_log": {"management_channel_id": legacy["management_channel_id"]}}.get(module_id, {})
        return {"enabled": False, "settings": defaults}

    def set_module(self, guild_id: int, module_id: str, *, enabled: bool, settings: dict[str, Any] | None = None) -> None:
        current = self.get_module(guild_id, module_id)
        values = current["settings"] if settings is None else settings
        with self._connection() as connection:
            connection.execute("""INSERT INTO guild_modules (guild_id, module_id, enabled, settings_json) VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, module_id) DO UPDATE SET enabled = excluded.enabled, settings_json = excluded.settings_json""", (guild_id, module_id, int(enabled), json.dumps(values)))

    def module_enabled(self, guild_id: int, module_id: str) -> bool:
        return self.get_module(guild_id, module_id)["enabled"]

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
