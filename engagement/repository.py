"""Engagement persistence; schema is managed by the migration CLI."""
import json
import time
from pathlib import Path
from typing import Any

from database import require_current, transaction


class EngagementRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        require_current(self.database_path)

    def _connection(self):
        return transaction(self.database_path)

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
