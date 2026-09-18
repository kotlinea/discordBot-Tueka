"""Social persistence; schema is managed by the migration CLI."""
import json
from contextlib import nullcontext
import time
import uuid
from typing import Any

from jobs import QueueRepository, QueueSpec
from database import IntegrityError, lock_resource, require_current, transaction


class SocialRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        require_current(self.database_url)
        self.event_jobs = QueueRepository(self.database_url, QueueSpec('social_events', completed='processed_at'))

    def _connection(self):
        return transaction(self.database_url)

    def social_subscriptions(self, guild_id: int, provider: str | None = None) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM social_subscriptions WHERE guild_id=%s", [guild_id]
        if provider:
            query += " AND provider=%s"
            params.append(provider)
        query += " ORDER BY provider, account_name"
        with self._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._social_subscription_row(row) for row in rows]

    @staticmethod
    def _social_subscription_row(row: dict[str, Any]) -> dict[str, Any]:
        value = dict(row)
        value["events"] = json.loads(value.pop("events_json"))
        value["event_channels"] = json.loads(value.pop("event_channels_json", "{}"))
        value["templates"] = json.loads(value.pop("templates_json", "{}"))
        return value

    def social_subscription(self, subscription_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM social_subscriptions WHERE id=%s", (subscription_id,)).fetchone()
        return self._social_subscription_row(row) if row else None

    def matching_social_subscriptions(self, provider: str, account_id: str, event_type: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("""SELECT s.* FROM social_subscriptions s JOIN social_targets t ON t.id=s.target_id
                WHERE s.provider=%s AND (s.account_id=%s OR t.external_id=%s OR t.account_key=%s) AND s.enabled=1""",
                (provider, account_id, account_id, account_id.lower().lstrip("@"))).fetchall()
        return [self._social_subscription_row(row) for row in rows if event_type in json.loads(row["events_json"])]

    def ensure_social_target(self, provider: str, account_key: str, *, _conn=None) -> dict[str, Any]:
        if provider not in {"youtube", "twitch", "tiktok", "x", "instagram"} or not account_key:
            raise ValueError("Invalid social target")
        now = int(time.time())
        with (nullcontext(_conn) if _conn is not None else self._connection()) as connection:
            lock_resource(connection, "social-provider-targets", provider)
            connection.execute("""INSERT INTO social_targets(provider,account_key,handle,status,next_check_at,created_at,updated_at)
                VALUES(%s,%s,%s,'pending',0,%s,%s) ON CONFLICT(provider,account_key) DO UPDATE SET updated_at=excluded.updated_at""",
                (provider, account_key, account_key, now, now))
            row = connection.execute("SELECT * FROM social_targets WHERE provider=%s AND account_key=%s", (provider, account_key)).fetchone()
        return self._social_target_row(row)

    @staticmethod
    def _social_target_row(row: dict[str, Any]) -> dict[str, Any]:
        value = dict(row)
        value["cursor"] = json.loads(value.pop("cursor_json"))
        return value

    def social_target(self, target_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM social_targets WHERE id=%s", (target_id,)).fetchone()
        return self._social_target_row(row) if row else None

    def social_targets(self, provider: str | None = None) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM social_targets", []
        if provider:
            query, params = query + " WHERE provider=%s", [provider]
        with self._connection() as connection:
            rows = connection.execute(query + " ORDER BY id", params).fetchall()
        return [self._social_target_row(row) for row in rows]

    def save_social_subscription_v2(self, guild_id: int, provider: str, account_key: str, channel_id: int,
                                    events: list[str], event_channels: dict[str, int], templates: dict[str, Any],
                                    role_id: int | None = None, enabled: bool = True, *, subscription_id: int | None = None,
                                    expected_revision: int | None = None, max_count: int = 10) -> dict[str, Any]:
        now = int(time.time())
        with self._connection() as connection:
            lock_resource(connection, "social-provider-targets", provider)
            target = self.ensure_social_target(provider, account_key, _conn=connection)
            lock_resource(connection, "social-subscriptions", f"{guild_id}:{provider}")
            if subscription_id is None:
                count = connection.execute("SELECT COUNT(*) AS count FROM social_subscriptions WHERE guild_id=%s AND provider=%s", (guild_id, provider)).fetchone()["count"]
                if count >= max_count:
                    raise OverflowError("Provider account limit reached")
                try:
                    cursor = connection.execute("""INSERT INTO social_subscriptions
                        (guild_id,provider,account_id,account_name,channel_id,role_id,events_json,enabled,created_at,updated_at,target_id,event_channels_json,templates_json,status,revision)
                        VALUES(%s,%s,%s,%s,%s,%s, %s,%s,%s,%s, %s,%s,%s, 'pending',1) RETURNING id""",
                        (guild_id, provider, account_key, account_key, channel_id, role_id, json.dumps(events), int(enabled), now, now,
                         target["id"], json.dumps(event_channels), json.dumps(templates, ensure_ascii=False)))
                    subscription_id = int(cursor.fetchone()["id"])
                except IntegrityError as exc:
                    raise ValueError("Target is already registered") from exc
            else:
                current = connection.execute("SELECT revision FROM social_subscriptions WHERE id=%s AND guild_id=%s FOR UPDATE", (subscription_id, guild_id)).fetchone()
                if not current:
                    raise LookupError("Subscription not found")
                if expected_revision is not None and int(current["revision"]) != expected_revision:
                    raise RuntimeError("revision_conflict")
                connection.execute("""UPDATE social_subscriptions SET channel_id=%s,role_id=%s,events_json=%s,event_channels_json=%s,templates_json=%s,enabled=%s,updated_at=%s,revision=revision+1
                    WHERE id=%s AND guild_id=%s""", (channel_id, role_id, json.dumps(events), json.dumps(event_channels), json.dumps(templates, ensure_ascii=False), int(enabled), now, subscription_id, guild_id))
            row = connection.execute("SELECT * FROM social_subscriptions WHERE id=%s", (subscription_id,)).fetchone()
        return self._social_subscription_row(row)

    def request_social_target_retry(self, target_id: int) -> None:
        with self._connection() as connection:
            connection.execute("UPDATE social_targets SET status='pending',last_error=NULL,next_check_at=0,lease_owner=NULL,lease_until=NULL,revision=revision+1,updated_at=%s WHERE id=%s", (int(time.time()), target_id))

    def wake_social_target(self, provider: str, account_id: str) -> int:
        with self._connection() as connection:
            result = connection.execute("""UPDATE social_targets SET next_check_at=0,updated_at=%s
                WHERE provider=%s AND (external_id=%s OR account_key=%s)""", (int(time.time()), provider, account_id, account_id))
        return int(result.rowcount)

    def invalidate_social_target(self, provider: str, account_id: str, error: str) -> int:
        now = int(time.time())
        with self._connection() as connection:
            lock_resource(connection, "social-provider-targets", provider)
            rows = connection.execute("SELECT id,cursor_json FROM social_targets WHERE provider=%s AND (external_id=%s OR account_key=%s) FOR UPDATE", (provider, account_id, account_id)).fetchall()
            for row in rows:
                cursor = json.loads(row["cursor_json"])
                cursor.pop("eventsub_synced_at", None)
                cursor.pop("websub_renew_at", None)
                connection.execute("UPDATE social_targets SET status='degraded',cursor_json=%s,last_error=%s,next_check_at=0,updated_at=%s WHERE id=%s",
                                   (json.dumps(cursor), error[:500], now, row["id"]))
                connection.execute("UPDATE social_subscriptions SET status='degraded',last_error=%s,updated_at=%s WHERE target_id=%s", (error[:500], now, row["id"]))
        return len(rows)

    def claim_social_targets(self, owner: str, *, limit: int = 20, lease_seconds: int = 60) -> list[dict[str, Any]]:
        now = int(time.time())
        with self._connection() as connection:
            rows = connection.execute("""SELECT * FROM social_targets WHERE next_check_at<=%s AND (lease_until IS NULL OR lease_until<%s)
                AND (status='orphaned' OR EXISTS(SELECT 1 FROM social_subscriptions s WHERE s.target_id=social_targets.id AND s.enabled=1))
                ORDER BY next_check_at,id LIMIT %s FOR UPDATE SKIP LOCKED""", (now, now, max(1, min(limit, 100)))).fetchall()
            claimed = []
            for row in rows:
                claim_owner = f"{owner}:{uuid.uuid4().hex}"
                connection.execute("UPDATE social_targets SET lease_owner=%s,lease_until=%s WHERE id=%s",
                                   (claim_owner, now + lease_seconds, row['id']))
                claimed.append({**self._social_target_row(row), 'lease_owner': claim_owner,
                                'lease_until': now + lease_seconds})
        return claimed

    def complete_social_target(self, target_id: int, owner: str, *, status: str, cursor: dict[str, Any], next_check_at: int,
                               external_id: str | None = None, handle: str | None = None, display_name: str | None = None,
                               avatar_url: str | None = None, error: str | None = None,
                               events: list[dict[str, Any]] | None = None) -> bool:
        now = int(time.time())
        with self._connection() as connection:
            provider_row = connection.execute('SELECT provider FROM social_targets WHERE id=%s', (target_id,)).fetchone()
            if provider_row is None:
                return False
            lock_resource(connection, "social-provider-targets", provider_row['provider'])
            current = connection.execute("SELECT provider FROM social_targets WHERE id=%s AND lease_owner=%s AND lease_until>%s FOR UPDATE", (target_id, owner, now)).fetchone()
            if not current:
                return False
            for event in events or []:
                self._enqueue_event(connection, current['provider'], event['external_id'], event['account_id'],
                                    event['event_type'], event['payload'], occurred_at=event.get('occurred_at'))
            if external_id:
                canonical = connection.execute(
                    "SELECT id,status,last_error FROM social_targets WHERE provider=%s AND external_id=%s AND id<>%s ORDER BY id LIMIT 1",
                    (current["provider"], external_id, target_id),
                ).fetchone()
                if canonical:
                    canonical_id = int(canonical["id"])
                    connection.execute("UPDATE social_subscriptions SET target_id=%s,status=%s,last_error=%s,updated_at=%s WHERE target_id=%s",
                                       (canonical_id, canonical["status"], canonical["last_error"], now, target_id))
                    deleted = connection.execute("DELETE FROM social_targets WHERE id=%s AND lease_owner=%s", (target_id, owner))
                    return deleted.rowcount == 1
            cursor_result = connection.execute("""UPDATE social_targets SET external_id=COALESCE(%s,external_id),handle=COALESCE(%s,handle),
                display_name=COALESCE(%s,display_name),avatar_url=COALESCE(%s,avatar_url),status=%s,cursor_json=%s,last_error=%s,last_checked_at=%s,next_check_at=%s,
                lease_owner=NULL,lease_until=NULL,revision=revision+1,updated_at=%s WHERE id=%s AND lease_owner=%s""",
                (external_id, handle, display_name, avatar_url, status, json.dumps(cursor), error, now, next_check_at, now, target_id, owner))
            connection.execute("UPDATE social_subscriptions SET status=%s,last_error=%s,updated_at=%s WHERE target_id=%s", (status, error, now, target_id))
        return cursor_result.rowcount == 1

    def social_worker_heartbeat(self, worker_name: str, details: dict[str, Any] | None = None) -> None:
        with self._connection() as connection:
            connection.execute("""INSERT INTO social_worker_state(worker_name,heartbeat_at,details_json) VALUES(%s,%s,%s)
                ON CONFLICT(worker_name) DO UPDATE SET heartbeat_at=excluded.heartbeat_at,details_json=excluded.details_json""",
                (worker_name, int(time.time()), json.dumps(details or {})))

    def social_worker_health(self) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM social_worker_state ORDER BY heartbeat_at DESC LIMIT 1").fetchone()
        return {**dict(row), "details": json.loads(row["details_json"])} if row else None

    def delete_social_subscription(self, guild_id: int, subscription_id: int, *, expected_revision: int | None = None) -> None:
        with self._connection() as connection:
            provider_row = connection.execute('SELECT provider FROM social_subscriptions WHERE guild_id=%s AND id=%s', (guild_id, subscription_id)).fetchone()
            if provider_row:
                lock_resource(connection, "social-provider-targets", provider_row['provider'])
            row = connection.execute("SELECT target_id,revision FROM social_subscriptions WHERE guild_id=%s AND id=%s FOR UPDATE", (guild_id, subscription_id)).fetchone()
            if expected_revision is not None and (row is None or row['revision'] != expected_revision):
                raise RuntimeError('revision_conflict')
            connection.execute("DELETE FROM social_subscriptions WHERE guild_id=%s AND id=%s", (guild_id, subscription_id))
            if row and row["target_id"] is not None:
                remaining = connection.execute("SELECT COUNT(*) AS count FROM social_subscriptions WHERE target_id=%s", (row["target_id"],)).fetchone()["count"]
                if not remaining:
                    connection.execute("UPDATE social_targets SET status='orphaned',next_check_at=0,lease_owner=NULL,lease_until=NULL,updated_at=%s WHERE id=%s", (int(time.time()), row["target_id"]))

    def delete_social_target(self, target_id: int, owner: str) -> bool:
        with self._connection() as connection:
            provider_row = connection.execute('SELECT provider FROM social_targets WHERE id=%s', (target_id,)).fetchone()
            if provider_row is None:
                return False
            lock_resource(connection, "social-provider-targets", provider_row['provider'])
            result = connection.execute("DELETE FROM social_targets WHERE id=%s AND lease_owner=%s AND lease_until>%s AND NOT EXISTS(SELECT 1 FROM social_subscriptions WHERE target_id=%s)", (target_id, owner, int(time.time()), target_id))
        return result.rowcount == 1

    def social_connection(self, guild_id: int, provider: str, account_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM social_connections WHERE guild_id=%s AND provider=%s AND account_id=%s", (guild_id, provider, account_id)).fetchone()
        return dict(row) if row else None

    def social_connections(self, guild_id: int, provider: str | None = None) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM social_connections WHERE guild_id=%s", [guild_id]
        if provider:
            query += " AND provider=%s"
            params.append(provider)
        with self._connection() as connection:
            rows = connection.execute(query + " ORDER BY provider, account_name", params).fetchall()
        return [dict(row) for row in rows]

    def save_social_connection(self, guild_id: int, provider: str, account_id: str, account_name: str, access_token_encrypted: str, refresh_token_encrypted: str | None, expires_at: int | None) -> None:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("INSERT INTO social_connections(guild_id,provider,account_id,account_name,access_token_encrypted,refresh_token_encrypted,expires_at,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(guild_id,provider,account_id) DO UPDATE SET account_name=excluded.account_name,access_token_encrypted=excluded.access_token_encrypted,refresh_token_encrypted=excluded.refresh_token_encrypted,expires_at=excluded.expires_at,updated_at=excluded.updated_at", (guild_id, provider, account_id, account_name, access_token_encrypted, refresh_token_encrypted, expires_at, now, now))

    def create_social_oauth_state(self, state: str, guild_id: int, provider: str, *, ttl_seconds: int = 600) -> None:
        if provider not in {"tiktok", "instagram"}:
            raise ValueError("Unsupported social OAuth provider")
        with self._connection() as connection:
            connection.execute("DELETE FROM social_oauth_states WHERE expires_at < %s", (int(time.time()),))
            connection.execute("INSERT INTO social_oauth_states(state,guild_id,provider,expires_at) VALUES(%s,%s,%s,%s)", (state, guild_id, provider, int(time.time()) + ttl_seconds))

    def consume_social_oauth_state(self, state: str, provider: str) -> int | None:
        now = int(time.time())
        with self._connection() as connection:
            row = connection.execute("DELETE FROM social_oauth_states WHERE state=%s RETURNING guild_id,provider,expires_at", (state,)).fetchone()
        return int(row["guild_id"]) if row and row["provider"] == provider and row["expires_at"] >= now else None

    def enqueue_social_event_v2(self, provider: str, external_event_id: str, account_id: str, event_type: str,
                                payload: dict[str, Any], *, occurred_at: int | None = None) -> bool:
        with self._connection() as connection:
            return self._enqueue_event(connection, provider, external_event_id, account_id, event_type, payload,
                                       occurred_at=occurred_at)

    @staticmethod
    def _enqueue_event(connection, provider, external_event_id, account_id, event_type, payload, *, occurred_at=None):
        now = int(time.time())
        event_key = f"{provider}:{event_type}:{external_event_id}"
        cursor = connection.execute("""INSERT INTO social_events
            (provider,event_key,account_id,payload_json,received_at,event_type,external_event_id,occurred_at,status,available_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s, 'pending',%s) ON CONFLICT DO NOTHING""",
            (provider, event_key, account_id, json.dumps(payload, ensure_ascii=False), now, event_type, external_event_id, occurred_at or now, now))
        return cursor.rowcount == 1

    def pending_social_events(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM social_events WHERE processed_at IS NULL AND available_at<=%s ORDER BY id LIMIT 100", (int(time.time()),)).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]




    def social_delivery(self, subscription_id: int, event_key: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute('SELECT * FROM social_deliveries WHERE subscription_id=%s AND event_key=%s', (subscription_id, event_key)).fetchone()
        return dict(row) if row else None

    def record_social_delivery(self, subscription_id: int, event_key: str, channel_id: int, message_id: int | None, state: str = "sent") -> bool:
        now = int(time.time())
        with self._connection() as connection:
            cursor = connection.execute("INSERT INTO social_deliveries(subscription_id,event_key,discord_channel_id,discord_message_id,state,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", (subscription_id, event_key, channel_id, message_id, state, now, now))
            if cursor.rowcount == 0:
                row = connection.execute("SELECT state,next_attempt_at FROM social_deliveries WHERE subscription_id=%s AND event_key=%s", (subscription_id, event_key)).fetchone()
                return bool(row and row["state"] in {"pending", "retry", "uncertain"} and int(row["next_attempt_at"] or 0) <= now)
        return True

    def update_social_delivery(self, subscription_id: int, event_key: str, message_id: int, state: str = "sent") -> None:
        with self._connection() as connection:
            connection.execute("UPDATE social_deliveries SET discord_message_id=%s,state=%s,updated_at=%s WHERE subscription_id=%s AND event_key=%s", (message_id, state, int(time.time()), subscription_id, event_key))

    def fail_social_delivery(self, subscription_id: int, event_key: str, error: str, *, retry: bool, uncertain: bool = False) -> None:
        now = int(time.time())
        with self._connection() as connection:
            row = connection.execute("SELECT attempts FROM social_deliveries WHERE subscription_id=%s AND event_key=%s FOR UPDATE", (subscription_id, event_key)).fetchone()
            attempts = int(row["attempts"] if row else 0) + 1
            delay = min(3600, 15 * (2 ** min(attempts, 8))) if retry else 0
            connection.execute("""UPDATE social_deliveries SET state=%s,attempts=%s,next_attempt_at=%s,last_error=%s,updated_at=%s
                WHERE subscription_id=%s AND event_key=%s""", ("uncertain" if uncertain else "retry" if retry else "failed", attempts, now + delay, error[:500], now, subscription_id, event_key))

    def purge_social_history(self, *, retention_days: int = 30) -> int:
        cutoff = int(time.time()) - max(1, retention_days) * 86400
        with self._connection() as connection:
            delivery_count = connection.execute("DELETE FROM social_deliveries WHERE updated_at<%s AND state IN ('sent','failed')", (cutoff,)).rowcount
            event_count = connection.execute("DELETE FROM social_events WHERE processed_at IS NOT NULL AND processed_at<%s", (cutoff,)).rowcount
        return int(delivery_count + event_count)

    def set_social_live_message(self, subscription_id: int, provider: str, account_id: str, channel_id: int, message_id: int) -> None:
        with self._connection() as connection:
            connection.execute("INSERT INTO social_live_messages(subscription_id,provider,account_id,discord_channel_id,discord_message_id) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(subscription_id,provider,account_id) DO UPDATE SET discord_channel_id=excluded.discord_channel_id,discord_message_id=excluded.discord_message_id", (subscription_id, provider, account_id, channel_id, message_id))

    def social_live_message(self, subscription_id: int, provider: str, account_id: str) -> dict[str, int] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT discord_channel_id,discord_message_id FROM social_live_messages WHERE subscription_id=%s AND provider=%s AND account_id=%s", (subscription_id, provider, account_id)).fetchone()
        return dict(row) if row else None

    def clear_social_live_message(self, subscription_id: int, provider: str, account_id: str) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM social_live_messages WHERE subscription_id=%s AND provider=%s AND account_id=%s", (subscription_id, provider, account_id))
