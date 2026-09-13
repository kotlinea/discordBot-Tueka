"""Social persistence; schema is managed by the migration CLI."""
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from jobs import QueueRepository, QueueSpec
from database import require_current, transaction


class SocialRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        require_current(self.database_path)
        self.event_jobs = QueueRepository(self.database_path, QueueSpec('social_events', completed='processed_at'))

    def _connection(self):
        return transaction(self.database_path)

    def social_subscriptions(self, guild_id: int, provider: str | None = None) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM social_subscriptions WHERE guild_id=?", [guild_id]
        if provider:
            query += " AND provider=?"
            params.append(provider)
        query += " ORDER BY provider, account_name"
        with self._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._social_subscription_row(row) for row in rows]

    @staticmethod
    def _social_subscription_row(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["events"] = json.loads(value.pop("events_json"))
        value["event_channels"] = json.loads(value.pop("event_channels_json", "{}"))
        value["templates"] = json.loads(value.pop("templates_json", "{}"))
        return value

    def social_subscription(self, subscription_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM social_subscriptions WHERE id=?", (subscription_id,)).fetchone()
        return self._social_subscription_row(row) if row else None

    def matching_social_subscriptions(self, provider: str, account_id: str, event_type: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("""SELECT s.* FROM social_subscriptions s JOIN social_targets t ON t.id=s.target_id
                WHERE s.provider=? AND (s.account_id=? OR t.external_id=? OR t.account_key=?) AND s.enabled=1""",
                (provider, account_id, account_id, account_id.lower().lstrip("@"))).fetchall()
        return [self._social_subscription_row(row) for row in rows if event_type in json.loads(row["events_json"])]

    def ensure_social_target(self, provider: str, account_key: str) -> dict[str, Any]:
        if provider not in {"youtube", "twitch", "tiktok", "x", "instagram"} or not account_key:
            raise ValueError("Invalid social target")
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("""INSERT INTO social_targets(provider,account_key,handle,status,next_check_at,created_at,updated_at)
                VALUES(?,?,?,'pending',0,?,?) ON CONFLICT(provider,account_key) DO UPDATE SET updated_at=excluded.updated_at""",
                (provider, account_key, account_key, now, now))
            row = connection.execute("SELECT * FROM social_targets WHERE provider=? AND account_key=?", (provider, account_key)).fetchone()
        return self._social_target_row(row)

    @staticmethod
    def _social_target_row(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["cursor"] = json.loads(value.pop("cursor_json"))
        return value

    def social_target(self, target_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM social_targets WHERE id=?", (target_id,)).fetchone()
        return self._social_target_row(row) if row else None

    def social_targets(self, provider: str | None = None) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM social_targets", []
        if provider:
            query, params = query + " WHERE provider=?", [provider]
        with self._connection() as connection:
            rows = connection.execute(query + " ORDER BY id", params).fetchall()
        return [self._social_target_row(row) for row in rows]

    def save_social_subscription_v2(self, guild_id: int, provider: str, account_key: str, channel_id: int,
                                    events: list[str], event_channels: dict[str, int], templates: dict[str, Any],
                                    role_id: int | None = None, enabled: bool = True, *, subscription_id: int | None = None,
                                    expected_revision: int | None = None, max_count: int = 10) -> dict[str, Any]:
        target = self.ensure_social_target(provider, account_key)
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if subscription_id is None:
                count = connection.execute("SELECT COUNT(*) FROM social_subscriptions WHERE guild_id=? AND provider=?", (guild_id, provider)).fetchone()[0]
                if count >= max_count:
                    raise OverflowError("Provider account limit reached")
                try:
                    cursor = connection.execute("""INSERT INTO social_subscriptions
                        (guild_id,provider,account_id,account_name,channel_id,role_id,events_json,enabled,created_at,updated_at,target_id,event_channels_json,templates_json,status,revision)
                        VALUES(?,?,?,?,?,?, ?,?,?,?, ?,?,?, 'pending',1)""",
                        (guild_id, provider, account_key, account_key, channel_id, role_id, json.dumps(events), int(enabled), now, now,
                         target["id"], json.dumps(event_channels), json.dumps(templates, ensure_ascii=False)))
                    subscription_id = int(cursor.lastrowid)
                except sqlite3.IntegrityError as exc:
                    raise ValueError("Target is already registered") from exc
            else:
                current = connection.execute("SELECT revision FROM social_subscriptions WHERE id=? AND guild_id=?", (subscription_id, guild_id)).fetchone()
                if not current:
                    raise LookupError("Subscription not found")
                if expected_revision is not None and int(current["revision"]) != expected_revision:
                    raise RuntimeError("revision_conflict")
                connection.execute("""UPDATE social_subscriptions SET channel_id=?,role_id=?,events_json=?,event_channels_json=?,templates_json=?,enabled=?,updated_at=?,revision=revision+1
                    WHERE id=? AND guild_id=?""", (channel_id, role_id, json.dumps(events), json.dumps(event_channels), json.dumps(templates, ensure_ascii=False), int(enabled), now, subscription_id, guild_id))
            row = connection.execute("SELECT * FROM social_subscriptions WHERE id=?", (subscription_id,)).fetchone()
        return self._social_subscription_row(row)

    def request_social_target_retry(self, target_id: int) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE social_targets SET status='pending',last_error=NULL,next_check_at=0,lease_owner=NULL,lease_until=NULL,revision=revision+1,updated_at=? WHERE id=?", (int(time.time()), target_id))

    def wake_social_target(self, provider: str, account_id: str) -> int:
        with self._connection() as connection:
            result = connection.execute("""UPDATE social_targets SET next_check_at=0,updated_at=?
                WHERE provider=? AND (external_id=? OR account_key=?)""", (int(time.time()), provider, account_id, account_id))
        return int(result.rowcount)

    def invalidate_social_target(self, provider: str, account_id: str, error: str) -> int:
        now = int(time.time())
        with self._connection() as connection:
            rows = connection.execute("SELECT id,cursor_json FROM social_targets WHERE provider=? AND (external_id=? OR account_key=?)", (provider, account_id, account_id)).fetchall()
            for row in rows:
                cursor = json.loads(row["cursor_json"])
                cursor.pop("eventsub_synced_at", None)
                cursor.pop("websub_renew_at", None)
                connection.execute("UPDATE social_targets SET status='degraded',cursor_json=?,last_error=?,next_check_at=0,updated_at=? WHERE id=?",
                                   (json.dumps(cursor), error[:500], now, row["id"]))
                connection.execute("UPDATE social_subscriptions SET status='degraded',last_error=?,updated_at=? WHERE target_id=?", (error[:500], now, row["id"]))
        return len(rows)

    def claim_social_targets(self, owner: str, *, limit: int = 20, lease_seconds: int = 60) -> list[dict[str, Any]]:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute("""SELECT * FROM social_targets WHERE next_check_at<=? AND (lease_until IS NULL OR lease_until<?)
                AND (status='orphaned' OR EXISTS(SELECT 1 FROM social_subscriptions s WHERE s.target_id=social_targets.id AND s.enabled=1))
                ORDER BY next_check_at,id LIMIT ?""", (now, now, max(1, min(limit, 100)))).fetchall()
            ids = [int(row["id"]) for row in rows]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                connection.execute(f"UPDATE social_targets SET lease_owner=?,lease_until=? WHERE id IN ({placeholders})", (owner, now + lease_seconds, *ids))
        return [self._social_target_row(row) for row in rows]

    def complete_social_target(self, target_id: int, owner: str, *, status: str, cursor: dict[str, Any], next_check_at: int,
                               external_id: str | None = None, handle: str | None = None, display_name: str | None = None,
                               avatar_url: str | None = None, error: str | None = None) -> bool:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute("SELECT provider FROM social_targets WHERE id=? AND lease_owner=?", (target_id, owner)).fetchone()
            if not current:
                return False
            if external_id:
                canonical = connection.execute(
                    "SELECT id,status,last_error FROM social_targets WHERE provider=? AND external_id=? AND id<>? ORDER BY id LIMIT 1",
                    (current["provider"], external_id, target_id),
                ).fetchone()
                if canonical:
                    canonical_id = int(canonical["id"])
                    connection.execute("UPDATE social_subscriptions SET target_id=?,status=?,last_error=?,updated_at=? WHERE target_id=?",
                                       (canonical_id, canonical["status"], canonical["last_error"], now, target_id))
                    deleted = connection.execute("DELETE FROM social_targets WHERE id=? AND lease_owner=?", (target_id, owner))
                    return deleted.rowcount == 1
            cursor_result = connection.execute("""UPDATE social_targets SET external_id=COALESCE(?,external_id),handle=COALESCE(?,handle),
                display_name=COALESCE(?,display_name),avatar_url=COALESCE(?,avatar_url),status=?,cursor_json=?,last_error=?,last_checked_at=?,next_check_at=?,
                lease_owner=NULL,lease_until=NULL,revision=revision+1,updated_at=? WHERE id=? AND lease_owner=?""",
                (external_id, handle, display_name, avatar_url, status, json.dumps(cursor), error, now, next_check_at, now, target_id, owner))
            connection.execute("UPDATE social_subscriptions SET status=?,last_error=?,updated_at=? WHERE target_id=?", (status, error, now, target_id))
        return cursor_result.rowcount == 1

    def social_worker_heartbeat(self, worker_name: str, details: dict[str, Any] | None = None) -> None:
        with self._connection() as connection:
            connection.execute("""INSERT INTO social_worker_state(worker_name,heartbeat_at,details_json) VALUES(?,?,?)
                ON CONFLICT(worker_name) DO UPDATE SET heartbeat_at=excluded.heartbeat_at,details_json=excluded.details_json""",
                (worker_name, int(time.time()), json.dumps(details or {})))

    def social_worker_health(self) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM social_worker_state ORDER BY heartbeat_at DESC LIMIT 1").fetchone()
        return {**dict(row), "details": json.loads(row["details_json"])} if row else None

    def delete_social_subscription(self, guild_id: int, subscription_id: int) -> None:
        with self._connection() as connection:
            row = connection.execute("SELECT target_id FROM social_subscriptions WHERE guild_id=? AND id=?", (guild_id, subscription_id)).fetchone()
            connection.execute("DELETE FROM social_subscriptions WHERE guild_id=? AND id=?", (guild_id, subscription_id))
            if row and row["target_id"] is not None:
                remaining = connection.execute("SELECT COUNT(*) FROM social_subscriptions WHERE target_id=?", (row["target_id"],)).fetchone()[0]
                if not remaining:
                    connection.execute("UPDATE social_targets SET status='orphaned',next_check_at=0,lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?", (int(time.time()), row["target_id"]))

    def delete_social_target(self, target_id: int, owner: str) -> bool:
        with self._connection() as connection:
            result = connection.execute("DELETE FROM social_targets WHERE id=? AND lease_owner=? AND NOT EXISTS(SELECT 1 FROM social_subscriptions WHERE target_id=?)", (target_id, owner, target_id))
        return result.rowcount == 1

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

    def enqueue_social_event_v2(self, provider: str, external_event_id: str, account_id: str, event_type: str,
                                payload: dict[str, Any], *, occurred_at: int | None = None) -> bool:
        event_key = f"{provider}:{event_type}:{external_event_id}"
        now = int(time.time())
        with self._connection() as connection:
            cursor = connection.execute("""INSERT OR IGNORE INTO social_events
                (provider,event_key,account_id,payload_json,received_at,event_type,external_event_id,occurred_at,status,available_at)
                VALUES(?,?,?,?,?,?,?,?, 'pending',?)""",
                (provider, event_key, account_id, json.dumps(payload, ensure_ascii=False), now, event_type, external_event_id, occurred_at or now, now))
        return cursor.rowcount == 1

    def pending_social_events(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM social_events WHERE processed_at IS NULL AND available_at<=? ORDER BY id LIMIT 100", (int(time.time()),)).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]




    def record_social_delivery(self, subscription_id: int, event_key: str, channel_id: int, message_id: int | None, state: str = "sent") -> bool:
        now = int(time.time())
        with self._connection() as connection:
            cursor = connection.execute("INSERT OR IGNORE INTO social_deliveries(subscription_id,event_key,discord_channel_id,discord_message_id,state,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (subscription_id, event_key, channel_id, message_id, state, now, now))
            if cursor.rowcount == 0:
                row = connection.execute("SELECT state,next_attempt_at FROM social_deliveries WHERE subscription_id=? AND event_key=?", (subscription_id, event_key)).fetchone()
                return bool(row and row["state"] in {"pending", "retry"} and int(row["next_attempt_at"] or 0) <= now)
        return True

    def update_social_delivery(self, subscription_id: int, event_key: str, message_id: int, state: str = "sent") -> None:
        with self._connection() as connection:
            connection.execute("UPDATE social_deliveries SET discord_message_id=?,state=?,updated_at=? WHERE subscription_id=? AND event_key=?", (message_id, state, int(time.time()), subscription_id, event_key))

    def fail_social_delivery(self, subscription_id: int, event_key: str, error: str, *, retry: bool) -> None:
        now = int(time.time())
        with self._connection() as connection:
            row = connection.execute("SELECT attempts FROM social_deliveries WHERE subscription_id=? AND event_key=?", (subscription_id, event_key)).fetchone()
            attempts = int(row["attempts"] if row else 0) + 1
            delay = min(3600, 15 * (2 ** min(attempts, 8))) if retry else 0
            connection.execute("""UPDATE social_deliveries SET state=?,attempts=?,next_attempt_at=?,last_error=?,updated_at=?
                WHERE subscription_id=? AND event_key=?""", ("retry" if retry else "failed", attempts, now + delay, error[:500], now, subscription_id, event_key))

    def purge_social_history(self, *, retention_days: int = 30) -> int:
        cutoff = int(time.time()) - max(1, retention_days) * 86400
        with self._connection() as connection:
            delivery_count = connection.execute("DELETE FROM social_deliveries WHERE updated_at<? AND state IN ('sent','failed')", (cutoff,)).rowcount
            event_count = connection.execute("DELETE FROM social_events WHERE processed_at IS NOT NULL AND processed_at<?", (cutoff,)).rowcount
        return int(delivery_count + event_count)

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
