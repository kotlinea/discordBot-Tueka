"""Guild module settings persistence shared by Dashboard and runtime domains."""
import json
from collections.abc import Iterable
from typing import Any

from contextlib import nullcontext
from database import require_current, transaction, lock_resource
from .registry import normalize


class GuildSettingsRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        require_current(self.database_url)

    def _connection(self):
        return transaction(self.database_url)

    def get_module(self, guild_id: int, module_id: str, *, _conn=None) -> dict[str, Any]:
        with (nullcontext(_conn) if _conn is not None else self._connection()) as connection:
            row = connection.execute("SELECT enabled, settings_json, revision FROM guild_modules WHERE guild_id = %s AND module_id = %s", (guild_id, module_id)).fetchone()
        return self._module(module_id, row)

    @staticmethod
    def _module(module_id: str, row) -> dict[str, Any]:
        if row:
            settings = normalize(module_id, json.loads(row["settings_json"]))
            return {"enabled": bool(row["enabled"]), "settings": settings, "revision": int(row["revision"])}
        return {"enabled": False, "settings": normalize(module_id, None), "revision": 0}

    def get_modules(self, guild_id: int, module_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        ids = list(dict.fromkeys(module_ids))
        if not ids:
            return {}
        with self._connection() as connection:
            rows = connection.execute("SELECT module_id, enabled, settings_json, revision FROM guild_modules WHERE guild_id=%s AND module_id=ANY(%s)", (guild_id, ids)).fetchall()
        stored = {row["module_id"]: row for row in rows}
        return {module_id: self._module(module_id, stored.get(module_id)) for module_id in ids}

    def set_module(self, guild_id: int, module_id: str, *, enabled: bool, settings: dict[str, Any] | None = None,
                   expected_revision: int | None = None) -> dict[str, Any]:
        with self._connection() as connection:
            lock_resource(connection, 'guild-module', f'{guild_id}:{module_id}')
            current = self.get_module(guild_id, module_id, _conn=connection)
            if expected_revision is not None and current["revision"] != expected_revision:
                raise RuntimeError("revision_conflict")
            values = current["settings"] if settings is None else settings
            connection.execute("""INSERT INTO guild_modules (guild_id, module_id, enabled, settings_json, revision) VALUES (%s, %s, %s, %s, 1)
                ON CONFLICT(guild_id, module_id) DO UPDATE SET enabled = excluded.enabled,
                settings_json = excluded.settings_json, revision = guild_modules.revision + 1""",
                (guild_id, module_id, int(enabled), json.dumps(values)))
            return self.get_module(guild_id, module_id, _conn=connection)

    def module_enabled(self, guild_id: int, module_id: str) -> bool:
        with self._connection() as connection:
            row = connection.execute("SELECT enabled FROM guild_modules WHERE guild_id=%s AND module_id=%s", (guild_id, module_id)).fetchone()
        return bool(row and row["enabled"])

    def enabled_module_guild_ids(self, module_id: str) -> list[int]:
        with self._connection() as connection:
            rows = connection.execute("SELECT guild_id FROM guild_modules WHERE module_id=%s AND enabled=1", (module_id,)).fetchall()
        return [row["guild_id"] for row in rows]
