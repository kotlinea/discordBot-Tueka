"""Guild module settings persistence shared by Dashboard and runtime domains."""
import json
from typing import Any

from contextlib import nullcontext
from database import require_current, transaction, lock_resource
from suggestions import normalize_settings as normalize_suggestion_settings
from .models import (welcome_settings, template_module_settings, audit_log_settings,
                     leveling_settings, automod_settings, moderation_settings, moderation_submodule_settings)


class GuildSettingsRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        require_current(self.database_url)

    def _connection(self):
        return transaction(self.database_url)

    def get_module(self, guild_id: int, module_id: str, *, _conn=None) -> dict[str, Any]:
        with (nullcontext(_conn) if _conn is not None else self._connection()) as connection:
            row = connection.execute("SELECT enabled, settings_json, revision FROM guild_modules WHERE guild_id = %s AND module_id = %s", (guild_id, module_id)).fetchone()
        if row:
            settings = json.loads(row["settings_json"])
            if module_id == "welcome":
                settings = welcome_settings(settings)
            elif module_id in {"live_stats", "temporary_voice"}:
                settings = template_module_settings(module_id, settings)
            elif module_id == "audit_log":
                settings = audit_log_settings(settings)
            elif module_id == "leveling":
                settings = leveling_settings(settings)
            elif module_id == "automod":
                settings = automod_settings(settings)
            elif module_id == "moderation":
                settings = moderation_settings(settings)
            elif module_id in {"anti_spam", "anti_raid", "infractions", "moderation_actions", "moderation_logs"}:
                settings = moderation_submodule_settings(module_id, settings)
            elif module_id == "suggestions":
                settings = normalize_suggestion_settings(settings)
            return {"enabled": bool(row["enabled"]), "settings": settings, "revision": int(row["revision"])}
        defaults = {"welcome": welcome_settings({}), "leveling": leveling_settings({}), "autorole": {"default_role_id": None}, "audit_log": audit_log_settings({}), "automod": automod_settings({}), "moderation": moderation_settings({}), "live_stats": template_module_settings("live_stats", {}), "temporary_voice": template_module_settings("temporary_voice", {}), "suggestions": normalize_suggestion_settings({})}.get(module_id, moderation_submodule_settings(module_id, {}) if module_id in {"anti_spam", "anti_raid", "infractions", "moderation_actions", "moderation_logs"} else {})
        return {"enabled": False, "settings": defaults, "revision": 0}

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
        return self.get_module(guild_id, module_id)["enabled"]

    def enabled_module_guild_ids(self, module_id: str) -> list[int]:
        with self._connection() as connection:
            rows = connection.execute("SELECT guild_id FROM guild_modules WHERE module_id=%s AND enabled=1", (module_id,)).fetchall()
        return [row["guild_id"] for row in rows]

