"""Community persistence for temporary voice and text/voice leveling."""
import time
from pathlib import Path
from database import require_current, transaction


class CommunityRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        require_current(self.database_path)

    def _connection(self):
        return transaction(self.database_path)

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

