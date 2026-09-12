"""SQLite persistence for suggestions, votes, and review history."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from database import require_current, transaction
from typing import Any


class SuggestionRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        require_current(self.database_path)

    def _connection(self):
        return transaction(self.database_path)

    @staticmethod
    def _item(row: sqlite3.Row, *, upvotes: int = 0, downvotes: int = 0) -> dict[str, Any]:
        value = dict(row)
        value["answers"] = json.loads(value.pop("answers_json"))
        value["upvotes"], value["downvotes"] = upvotes, downvotes
        return value

    def create(self, guild_id: int, channel_id: int, author_id: int, answers: dict[str, str]) -> dict[str, Any]:
        now = int(time.time())
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO suggestions(guild_id,channel_id,author_id,answers_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (guild_id, channel_id, author_id, json.dumps(answers, ensure_ascii=False), now, now),
            )
            suggestion_id = int(cursor.lastrowid)
            connection.execute(
                "INSERT INTO suggestion_events(suggestion_id,guild_id,actor_id,event_type,created_at) VALUES(?,?,?,?,?)",
                (suggestion_id, guild_id, author_id, "created", now),
            )
        item = self.get(guild_id, suggestion_id)
        assert item is not None
        return item

    def attach_message(self, guild_id: int, suggestion_id: int, message_id: int) -> dict[str, Any]:
        with self._connection() as connection:
            connection.execute(
                "UPDATE suggestions SET message_id=?,updated_at=?,revision=revision+1 WHERE guild_id=? AND id=?",
                (message_id, int(time.time()), guild_id, suggestion_id),
            )
        item = self.get(guild_id, suggestion_id)
        if item is None:
            raise LookupError("suggestion_not_found")
        return item

    def mark_delivery_failed(self, guild_id: int, suggestion_id: int, detail: str) -> None:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("UPDATE suggestions SET status='delivery_failed',updated_at=?,revision=revision+1 WHERE guild_id=? AND id=?", (now, guild_id, suggestion_id))
            connection.execute(
                "INSERT INTO suggestion_events(suggestion_id,guild_id,actor_id,event_type,detail_json,created_at) SELECT id,guild_id,author_id,'delivery_failed',?,? FROM suggestions WHERE guild_id=? AND id=?",
                (json.dumps({"error": detail[:300]}, ensure_ascii=False), now, guild_id, suggestion_id),
            )

    def get(self, guild_id: int, suggestion_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM suggestions WHERE guild_id=? AND id=?", (guild_id, suggestion_id)).fetchone()
            if row is None:
                return None
            counts = connection.execute(
                "SELECT SUM(value=1) AS upvotes,SUM(value=-1) AS downvotes FROM suggestion_votes WHERE suggestion_id=?",
                (suggestion_id,),
            ).fetchone()
        return self._item(row, upvotes=int(counts["upvotes"] or 0), downvotes=int(counts["downvotes"] or 0))

    def list(self, guild_id: int, *, limit: int = 50, before: int | None = None) -> list[dict[str, Any]]:
        clauses, values = ["guild_id=?"], [guild_id]
        if before is not None:
            clauses.append("id<?")
            values.append(before)
        values.append(max(1, min(limit, 100)))
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM suggestions WHERE {' AND '.join(clauses)} ORDER BY id DESC LIMIT ?", values,
            ).fetchall()
            counts = {int(row["suggestion_id"]): (int(row["upvotes"] or 0), int(row["downvotes"] or 0)) for row in connection.execute(
                "SELECT suggestion_id,SUM(value=1) AS upvotes,SUM(value=-1) AS downvotes FROM suggestion_votes WHERE suggestion_id IN (SELECT id FROM suggestions WHERE guild_id=?) GROUP BY suggestion_id",
                (guild_id,),
            ).fetchall()}
        return [self._item(row, upvotes=counts.get(int(row["id"]), (0, 0))[0], downvotes=counts.get(int(row["id"]), (0, 0))[1]) for row in rows]

    def vote(self, guild_id: int, suggestion_id: int, user_id: int, value: int) -> dict[str, Any]:
        if value not in {-1, 1}:
            raise ValueError("invalid_vote")
        now = int(time.time())
        with self._connection() as connection:
            # Serialize the status check and vote with staff review writes.
            connection.execute("BEGIN IMMEDIATE")
            item = connection.execute("SELECT status FROM suggestions WHERE guild_id=? AND id=?", (guild_id, suggestion_id)).fetchone()
            if item is None:
                raise LookupError("suggestion_not_found")
            if item["status"] in {"approved", "rejected", "delivery_failed"}:
                raise RuntimeError("suggestion_closed")
            current = connection.execute("SELECT value FROM suggestion_votes WHERE suggestion_id=? AND user_id=?", (suggestion_id, user_id)).fetchone()
            if current and int(current["value"]) == value:
                connection.execute("DELETE FROM suggestion_votes WHERE suggestion_id=? AND user_id=?", (suggestion_id, user_id))
                event_type = "vote_removed"
            else:
                connection.execute(
                    "INSERT INTO suggestion_votes(suggestion_id,user_id,value,created_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(suggestion_id,user_id) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                    (suggestion_id, user_id, value, now, now),
                )
                event_type = "vote_cast"
            connection.execute(
                "INSERT INTO suggestion_events(suggestion_id,guild_id,actor_id,event_type,detail_json,created_at) VALUES(?,?,?,?,?,?)",
                (suggestion_id, guild_id, user_id, event_type, json.dumps({"value": value}), now),
            )
        result = self.get(guild_id, suggestion_id)
        assert result is not None
        return result

    def review(self, guild_id: int, suggestion_id: int, reviewer_id: int, status: str) -> dict[str, Any]:
        if status not in {"reviewing", "approved", "rejected"}:
            raise ValueError("invalid_status")
        now = int(time.time())
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE suggestions SET status=?,reviewer_id=?,reviewed_at=?,updated_at=?,revision=revision+1 WHERE guild_id=? AND id=? AND status IN ('pending','reviewing')",
                (status, reviewer_id, now, now, guild_id, suggestion_id),
            )
            if not cursor.rowcount:
                exists = connection.execute("SELECT 1 FROM suggestions WHERE guild_id=? AND id=?", (guild_id, suggestion_id)).fetchone()
                if exists:
                    raise RuntimeError("suggestion_closed")
                raise LookupError("suggestion_not_found")
            connection.execute(
                "INSERT INTO suggestion_events(suggestion_id,guild_id,actor_id,event_type,detail_json,created_at) VALUES(?,?,?,?,?,?)",
                (suggestion_id, guild_id, reviewer_id, "status_changed", json.dumps({"status": status}), now),
            )
        result = self.get(guild_id, suggestion_id)
        assert result is not None
        return result
