"""PostgreSQL persistence for suggestions, votes, and review history."""
from __future__ import annotations

import json
import time
from database import require_current, transaction
from jobs import QueueRepository, QueueSpec, LostLease
from jobs.catalog import QUEUE_SPECS
from typing import Any
from discord_io import DiscordFailure


class SuggestionRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        require_current(self.database_url)
        self.outbox_jobs = QueueRepository(self.database_url, QUEUE_SPECS['suggestion_outbox'])

    @staticmethod
    def _queue(connection, suggestion_id: int, action: str, payload: dict | None = None):
        now = int(time.time())
        connection.execute('INSERT INTO suggestion_outbox(suggestion_id,action,payload_json,available_at,created_at) VALUES(%s,%s,%s,%s,%s)',
                           (suggestion_id, action, json.dumps(payload or {}), now, now))

    def delivery_state(self, item: dict, *, started: bool, failed: str | None = None):
        with self._connection() as connection:
            changed = connection.execute("""UPDATE suggestion_outbox SET delivery_started=%s WHERE id=%s AND status='processing'
                AND lease_owner=%s AND lease_token=%s AND lease_until>%s""",
                (int(started), item['id'], item['_lease']['owner'], item['_lease']['token'], int(time.time())))
            if changed.rowcount != 1:
                raise LostLease('Suggestion delivery ownership changed')
            if failed is not None:
                connection.execute("UPDATE suggestions SET status='delivery_failed',updated_at=%s,revision=revision+1 WHERE id=%s AND message_id IS NULL", (int(time.time()), item['suggestion_id']))
                connection.execute("""INSERT INTO suggestion_events(suggestion_id,guild_id,actor_id,event_type,detail_json,created_at)
                    SELECT id,guild_id,author_id,'delivery_failed',%s,%s FROM suggestions WHERE id=%s""",
                    (json.dumps({'error': failed[:300]}), int(time.time()), item['suggestion_id']))

    def publication_delivered(self, item: dict, message_id: int, *, discussion: bool = False):
        with self._connection() as connection:
            owned = connection.execute("SELECT 1 FROM suggestion_outbox WHERE id=%s AND status='processing' AND lease_owner=%s AND lease_token=%s AND lease_until>%s FOR UPDATE",
                (item['id'], item['_lease']['owner'], item['_lease']['token'], int(time.time()))).fetchone()
            if not owned:
                raise LostLease('Suggestion delivery ownership changed')
            changed = connection.execute("UPDATE suggestions SET message_id=%s,status=CASE WHEN status='delivery_failed' THEN 'pending' ELSE status END,updated_at=%s,revision=revision+1 WHERE id=%s AND (message_id IS NULL OR message_id=%s)",
                (message_id, int(time.time()), item['suggestion_id'], message_id))
            if changed.rowcount != 1:
                raise DiscordFailure('Suggestion publication reference changed; reconciliation required', partial=True)
            self._queue(connection, item['suggestion_id'], 'sync')
            if discussion:
                self._queue(connection, item['suggestion_id'], 'discussion')

    def discussion_delivered(self, item: dict, thread_id: int):
        with self._connection() as connection:
            owned = connection.execute("SELECT 1 FROM suggestion_outbox WHERE id=%s AND status='processing' AND lease_owner=%s AND lease_token=%s AND lease_until>%s FOR UPDATE",
                (item['id'], item['_lease']['owner'], item['_lease']['token'], int(time.time()))).fetchone()
            if not owned:
                raise LostLease('Suggestion delivery ownership changed')
            changed = connection.execute('UPDATE suggestions SET discussion_thread_id=%s,revision=revision+1,updated_at=%s WHERE id=%s AND (discussion_thread_id IS NULL OR discussion_thread_id=%s)',
                (thread_id, int(time.time()), item['suggestion_id'], thread_id))
            if changed.rowcount != 1:
                raise DiscordFailure('Suggestion discussion reference changed; reconciliation required', partial=True)
            self._queue(connection, item['suggestion_id'], 'sync')

    def delivery_suggestion(self, suggestion_id: int) -> dict | None:
        with self._connection() as connection:
            row = connection.execute('SELECT guild_id FROM suggestions WHERE id=%s', (suggestion_id,)).fetchone()
        return self.get(row['guild_id'], suggestion_id) if row else None

    def _connection(self):
        return transaction(self.database_url)

    @staticmethod
    def _item(row: dict[str, Any], *, upvotes: int = 0, downvotes: int = 0) -> dict[str, Any]:
        value = dict(row)
        value["answers"] = json.loads(value.pop("answers_json"))
        value["upvotes"], value["downvotes"] = upvotes, downvotes
        return value

    def create(self, guild_id: int, channel_id: int, author_id: int, answers: dict[str, str]) -> dict[str, Any]:
        now = int(time.time())
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO suggestions(guild_id,channel_id,author_id,answers_json,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id",
                (guild_id, channel_id, author_id, json.dumps(answers, ensure_ascii=False), now, now),
            )
            suggestion_id = int(cursor.fetchone()["id"])
            connection.execute(
                "INSERT INTO suggestion_events(suggestion_id,guild_id,actor_id,event_type,created_at) VALUES(%s,%s,%s,%s,%s)",
                (suggestion_id, guild_id, author_id, "created", now),
            )
            self._queue(connection, suggestion_id, 'publish')
        item = self.get(guild_id, suggestion_id)
        assert item is not None
        return item

    def attach_message(self, guild_id: int, suggestion_id: int, message_id: int) -> dict[str, Any]:
        with self._connection() as connection:
            connection.execute(
                "UPDATE suggestions SET message_id=%s,updated_at=%s,revision=revision+1 WHERE guild_id=%s AND id=%s",
                (message_id, int(time.time()), guild_id, suggestion_id),
            )
        item = self.get(guild_id, suggestion_id)
        if item is None:
            raise LookupError("suggestion_not_found")
        return item

    def mark_delivery_failed(self, guild_id: int, suggestion_id: int, detail: str) -> None:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("UPDATE suggestions SET status='delivery_failed',updated_at=%s,revision=revision+1 WHERE guild_id=%s AND id=%s", (now, guild_id, suggestion_id))
            connection.execute(
                "INSERT INTO suggestion_events(suggestion_id,guild_id,actor_id,event_type,detail_json,created_at) SELECT id,guild_id,author_id,'delivery_failed',%s,%s FROM suggestions WHERE guild_id=%s AND id=%s",
                (json.dumps({"error": detail[:300]}, ensure_ascii=False), now, guild_id, suggestion_id),
            )

    def get(self, guild_id: int, suggestion_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM suggestions WHERE guild_id=%s AND id=%s", (guild_id, suggestion_id)).fetchone()
            if row is None:
                return None
            counts = connection.execute(
                "SELECT COUNT(*) FILTER (WHERE value=1) AS upvotes,COUNT(*) FILTER (WHERE value=-1) AS downvotes FROM suggestion_votes WHERE suggestion_id=%s",
                (suggestion_id,),
            ).fetchone()
        return self._item(row, upvotes=int(counts["upvotes"] or 0), downvotes=int(counts["downvotes"] or 0))

    def list(self, guild_id: int, *, limit: int = 50, before: int | None = None) -> list[dict[str, Any]]:
        clauses, values = ["guild_id=%s"], [guild_id]
        if before is not None:
            clauses.append("id<%s")
            values.append(before)
        values.append(max(1, min(limit, 100)))
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM suggestions WHERE {' AND '.join(clauses)} ORDER BY id DESC LIMIT %s", values,
            ).fetchall()
            counts = {int(row["suggestion_id"]): (int(row["upvotes"] or 0), int(row["downvotes"] or 0)) for row in connection.execute(
                "SELECT suggestion_id,COUNT(*) FILTER (WHERE value=1) AS upvotes,COUNT(*) FILTER (WHERE value=-1) AS downvotes FROM suggestion_votes WHERE suggestion_id IN (SELECT id FROM suggestions WHERE guild_id=%s) GROUP BY suggestion_id",
                (guild_id,),
            ).fetchall()}
        return [self._item(row, upvotes=counts.get(int(row["id"]), (0, 0))[0], downvotes=counts.get(int(row["id"]), (0, 0))[1]) for row in rows]

    def vote(self, guild_id: int, suggestion_id: int, user_id: int, value: int) -> dict[str, Any]:
        if value not in {-1, 1}:
            raise ValueError("invalid_vote")
        now = int(time.time())
        with self._connection() as connection:
            # Serialize the status check and vote with staff review writes.
            item = connection.execute("SELECT status FROM suggestions WHERE guild_id=%s AND id=%s FOR UPDATE", (guild_id, suggestion_id)).fetchone()
            if item is None:
                raise LookupError("suggestion_not_found")
            if item["status"] in {"approved", "rejected", "implemented", "delivery_failed"}:
                raise RuntimeError("suggestion_closed")
            current = connection.execute("SELECT value FROM suggestion_votes WHERE suggestion_id=%s AND user_id=%s", (suggestion_id, user_id)).fetchone()
            if current and int(current["value"]) == value:
                connection.execute("DELETE FROM suggestion_votes WHERE suggestion_id=%s AND user_id=%s", (suggestion_id, user_id))
                event_type = "vote_removed"
            else:
                connection.execute(
                    "INSERT INTO suggestion_votes(suggestion_id,user_id,value,created_at,updated_at) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(suggestion_id,user_id) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                    (suggestion_id, user_id, value, now, now),
                )
                event_type = "vote_cast"
            connection.execute(
                "INSERT INTO suggestion_events(suggestion_id,guild_id,actor_id,event_type,detail_json,created_at) VALUES(%s,%s,%s,%s,%s,%s)",
                (suggestion_id, guild_id, user_id, event_type, json.dumps({"value": value}), now),
            )
            self._queue(connection, suggestion_id, 'sync')
        result = self.get(guild_id, suggestion_id)
        assert result is not None
        return result

    def review(self, guild_id: int, suggestion_id: int, reviewer_id: int, status: str,
               reason: str = '', *, expected_revision: int | None = None) -> dict[str, Any]:
        if status not in {"reviewing", "approved", "rejected", "implemented"}:
            raise ValueError("invalid_status")
        reason = reason.strip()
        if not reason or len(reason) > 1000:
            raise ValueError('invalid_reason')
        now = int(time.time())
        with self._connection() as connection:
            previous = connection.execute('SELECT status,revision FROM suggestions WHERE guild_id=%s AND id=%s FOR UPDATE',
                (guild_id, suggestion_id)).fetchone()
            if previous is None:
                raise LookupError('suggestion_not_found')
            if expected_revision is not None and previous['revision'] != expected_revision:
                raise RuntimeError('revision_conflict')
            allowed = {'approved'} if status == 'implemented' else {'pending', 'reviewing'}
            if previous['status'] not in allowed:
                raise RuntimeError('suggestion_closed')
            cursor = connection.execute(
                "UPDATE suggestions SET status=%s,reviewer_id=%s,review_reason=%s,reviewed_at=%s,implemented_at=CASE WHEN %s='implemented' THEN %s ELSE implemented_at END,updated_at=%s,revision=revision+1 WHERE guild_id=%s AND id=%s",
                (status, reviewer_id, reason, now, status, now, now, guild_id, suggestion_id),
            )
            if not cursor.rowcount:
                exists = connection.execute("SELECT 1 FROM suggestions WHERE guild_id=%s AND id=%s", (guild_id, suggestion_id)).fetchone()
                if exists:
                    raise RuntimeError("suggestion_closed")
                raise LookupError("suggestion_not_found")
            connection.execute(
                "INSERT INTO suggestion_events(suggestion_id,guild_id,actor_id,event_type,detail_json,created_at) VALUES(%s,%s,%s,%s,%s,%s)",
                (suggestion_id, guild_id, reviewer_id, "status_changed", json.dumps({"status": status, 'previous_status': previous['status'], 'reason': reason}, ensure_ascii=False), now),
            )
            self._queue(connection, suggestion_id, 'sync')
            self._queue(connection, suggestion_id, 'review_log', {'status': status, 'reviewer_id': reviewer_id, 'review_reason': reason})
        result = self.get(guild_id, suggestion_id)
        assert result is not None
        return result

    def events(self, guild_id: int, suggestion_id: int, *, before: int | None = None, limit: int = 50) -> list[dict]:
        with self._connection() as connection:
            exists = connection.execute('SELECT 1 FROM suggestions WHERE guild_id=%s AND id=%s', (guild_id, suggestion_id)).fetchone()
            if not exists:
                raise LookupError('suggestion_not_found')
            rows = connection.execute('SELECT id,actor_id,event_type,detail_json,created_at FROM suggestion_events WHERE guild_id=%s AND suggestion_id=%s AND (%s::bigint IS NULL OR id<%s) ORDER BY id DESC LIMIT %s',
                (guild_id, suggestion_id, before, before, max(1, min(limit, 100)))).fetchall()
        return [{**{k:v for k,v in row.items() if k != 'detail_json'}, 'detail': json.loads(row['detail_json'])} for row in rows]
