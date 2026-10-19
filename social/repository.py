"""Social persistence; schema is managed by the migration CLI."""
import json
from contextlib import nullcontext
import time
import uuid
from typing import Any

from jobs import LostLease, QueueRepository, QueueSpec
from jobs.catalog import QUEUE_SPECS
from database import IntegrityError, lock_resource, require_current, transaction


class SocialEventQueue(QueueRepository):
    def _remaining_budget(self, connection, event_key):
        # Only the enabled recipient that spent its own budget is terminated.
        # A guild pause must never spend another recipient's attempts.
        connection.execute("""UPDATE social_deliveries d SET state='failed',
            last_error='Delivery retry limit reached',updated_at=%s
            FROM social_subscriptions s JOIN guild_modules g ON g.guild_id=s.guild_id
                AND g.module_id=s.provider || '_updates' AND g.enabled=1
            WHERE d.subscription_id=s.id AND d.event_key=%s AND d.attempts>=%s
                AND d.state IN ('pending','retry','uncertain')""",
            (int(self.clock()), event_key, self.spec.max_attempts))
        row = connection.execute("""SELECT MAX(attempts) AS remaining
            FROM social_deliveries WHERE event_key=%s
            AND state IN ('pending','retry','uncertain') AND attempts<%s""",
            (event_key, self.spec.max_attempts)).fetchone()
        if row['remaining'] is None:
            return None
        # Spend each new recipient attempt as dispatch progress only once.
        # Old terminal receipts cannot replenish retries for a dispatcher that
        # repeatedly fails before reserving any new I/O attempt.
        progress = connection.execute("""UPDATE social_deliveries d
            SET dispatch_accounted_attempts=d.attempts
            WHERE d.event_key=%s
            AND (d.state IN ('sent','failed') OR
                (d.state IN ('pending','retry','uncertain') AND EXISTS(
                    SELECT 1 FROM social_subscriptions s JOIN guild_modules g ON g.guild_id=s.guild_id
                        AND g.module_id=s.provider || '_updates' AND g.enabled=1
                    WHERE s.id=d.subscription_id)))
            AND d.attempts>d.dispatch_accounted_attempts RETURNING d.id""", (event_key,)).fetchall()
        return row['remaining'] if progress else None

    def _exhaust(self, connection, now, scope, scope_values):
        # Lock eligible final attempts in the same transaction as the next
        # claim. Rows skipped or outside this batch must not be exhausted by a
        # second, generic query that never reconciled their recipient budgets.
        rows = connection.execute(f"""SELECT id,event_key FROM social_events
            WHERE attempts>=%s AND status IN ('pending','retry','processing')
            AND (lease_until IS NULL OR lease_until<=%s){scope}
            ORDER BY id LIMIT 100 FOR UPDATE SKIP LOCKED""",
            (self.spec.max_attempts, now, *scope_values)).fetchall()
        for row in rows:
            remaining = self._remaining_budget(connection, row['event_key'])
            if remaining is not None:
                connection.execute("""UPDATE social_events SET attempts=%s,status='retry',processed_at=NULL,
                    lease_owner=NULL,lease_token=NULL,lease_until=NULL WHERE id=%s""", (remaining, row['id']))
            else:
                connection.execute("""UPDATE social_events SET status='failed',processed_at=%s,
                    last_error='Lease expired at retry limit',lease_owner=NULL,lease_token=NULL,lease_until=NULL
                    WHERE id=%s""", (int(self.clock()), row['id']))

    def _claim_scope(self):
        # Events are shared across guilds. An enabled unfinished recipient may
        # proceed while another guild's existing intent waits for re-enabling.
        recipients = """FROM social_subscriptions s JOIN social_targets t ON t.id=s.target_id
            LEFT JOIN guild_modules g ON g.guild_id=s.guild_id AND g.module_id=s.provider || '_updates'
            LEFT JOIN social_deliveries d ON d.subscription_id=s.id AND d.event_key=social_events.event_key
            WHERE s.provider=social_events.provider AND s.enabled=1
            AND (s.account_id=social_events.account_id OR t.external_id=social_events.account_id
                 OR t.account_key=ltrim(lower(social_events.account_id),'@'))
            AND s.events_json::jsonb ? social_events.event_type"""
        return (f" AND (NOT EXISTS(SELECT 1 {recipients} AND COALESCE(g.enabled,0)=0"
                " AND d.state IN ('pending','retry','uncertain'))"
                f" OR EXISTS(SELECT 1 {recipients} AND g.enabled=1"
                " AND (d.id IS NULL OR d.state IN ('pending','retry','uncertain')))"
                f" OR EXISTS(SELECT 1 {recipients} AND d.id IS NULL))", ())

    def finish(self, claim, outcome):
        if outcome.error is not None and outcome.retry and claim.attempt >= self.spec.max_attempts:
            try:
                with transaction(self.database_url) as connection:
                    if self._owned_at(connection, claim) is None:
                        return False
                    remaining = self._remaining_budget(connection, claim.payload['event_key'])
                    now = self._owned_at(connection, claim)
                    if now is None:
                        raise LostLease('Social event lease expired while reconciling recipient budgets')
                    changed = connection.execute("""UPDATE social_events SET status=%s,attempts=%s,
                        processed_at=%s,available_at=%s,last_error=%s,
                        lease_owner=NULL,lease_token=NULL,lease_until=NULL
                        WHERE id=%s AND lease_owner=%s AND lease_token=%s
                        AND lease_until>%s AND status='processing'""",
                        ('retry' if remaining is not None else 'failed',
                         remaining if remaining is not None else claim.attempt,
                         None if remaining is not None else now, claim.payload['available_at'], outcome.error[:500],
                         claim.id, claim.owner, claim.token, now)).rowcount == 1
                    if not changed:
                        raise LostLease('Social event lease lost before budget completion')
                return True
            except LostLease:
                return False
        if outcome.error is not None or not (outcome.result or {}).get('paused'):
            return super().finish(claim, outcome)
        # A pause is not a failed delivery attempt. Restore the claim's prior
        # retry budget and deadline; the scope will wake it when any guild can run.
        with transaction(self.database_url) as connection:
            if self._owned_at(connection, claim) is None:
                return False
            return connection.execute("""UPDATE social_events SET status=%s,attempts=attempts-1,
                available_at=%s,last_error=%s,processed_at=NULL,
                lease_owner=NULL,lease_token=NULL,lease_until=NULL
                WHERE id=%s AND lease_owner=%s AND lease_token=%s AND status='processing'""",
                ('pending' if claim.payload['status'] == 'pending' else 'retry',
                 claim.payload['available_at'], claim.payload.get('last_error'),
                 claim.id, claim.owner, claim.token)).rowcount == 1


class SocialRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        require_current(self.database_url)
        self.event_jobs = SocialEventQueue(self.database_url, QUEUE_SPECS['social_events'])

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
            if row['status'] == 'orphaned':
                row = self._resume_social_target(connection, row)
        return self._social_target_row(row)

    @staticmethod
    def _resume_social_target(connection, row):
        cursor = json.loads(row['cursor_json'])
        cursor.pop('websub_renew_at', None)
        cursor.pop('eventsub_synced_at', None)
        return connection.execute("""UPDATE social_targets SET status='pending',next_check_at=0,
            lease_owner=NULL,lease_until=NULL,cursor_json=%s,last_error=NULL,
            revision=revision+1,updated_at=%s WHERE id=%s RETURNING *""",
            (json.dumps(cursor), int(time.time()), row['id'])).fetchone()

    def resume_social_target_after_cleanup(self, target_id: int) -> None:
        """Reconcile an old unsubscribe that finished after references returned."""
        with self._connection() as connection:
            row = connection.execute('SELECT provider FROM social_targets WHERE id=%s', (target_id,)).fetchone()
            if row is None:
                return
            lock_resource(connection, 'social-provider-targets', row['provider'])
            row = connection.execute('SELECT * FROM social_targets WHERE id=%s FOR UPDATE', (target_id,)).fetchone()
            if row and connection.execute('SELECT 1 FROM social_subscriptions WHERE target_id=%s LIMIT 1', (target_id,)).fetchone():
                self._resume_social_target(connection, row)
                connection.execute("UPDATE social_subscriptions SET status='pending',last_error=NULL,updated_at=%s WHERE target_id=%s", (int(time.time()), target_id))

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
            result = connection.execute("""UPDATE social_targets SET next_check_at=0,wake_revision=wake_revision+1,updated_at=%s
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
                # In-flight polling owns the old subscription snapshot. Revoke
                # its claim so completion cannot restore the removed markers.
                connection.execute("UPDATE social_targets SET status='degraded',cursor_json=%s,last_error=%s,next_check_at=0,lease_owner=NULL,lease_until=NULL,updated_at=%s WHERE id=%s",
                                   (json.dumps(cursor), error[:500], now, row["id"]))
                connection.execute("UPDATE social_subscriptions SET status='degraded',last_error=%s,updated_at=%s WHERE target_id=%s", (error[:500], now, row["id"]))
        return len(rows)

    def claim_social_targets(self, owner: str, *, limit: int = 20, lease_seconds: int = 60) -> list[dict[str, Any]]:
        with self._connection() as connection:
            now = int(time.time())
            rows = connection.execute("""SELECT * FROM social_targets WHERE next_check_at<=%s AND (lease_until IS NULL OR lease_until<=%s)
                AND (status='orphaned' OR EXISTS(SELECT 1 FROM social_subscriptions s WHERE s.target_id=social_targets.id AND s.enabled=1))
                ORDER BY next_check_at,id LIMIT %s FOR UPDATE SKIP LOCKED""", (now, now, max(1, min(limit, 100)))).fetchall()
            claimed = []
            for row in rows:
                now = int(time.time())
                claim_owner = f"{owner}:{uuid.uuid4().hex}"
                connection.execute("UPDATE social_targets SET lease_owner=%s,lease_until=%s WHERE id=%s",
                                   (claim_owner, now + lease_seconds, row['id']))
                claimed.append({**self._social_target_row(row), 'lease_owner': claim_owner,
                                'lease_until': now + lease_seconds})
        return claimed

    def complete_social_target(self, target_id: int, owner: str, *, status: str, cursor: dict[str, Any], next_check_at: int,
                               external_id: str | None = None, handle: str | None = None, display_name: str | None = None,
                               avatar_url: str | None = None, error: str | None = None,
                               events: list[dict[str, Any]] | None = None,
                               observed_wake_revision: int | None = None) -> bool:
        with self._connection() as connection:
            provider_row = connection.execute('SELECT provider FROM social_targets WHERE id=%s', (target_id,)).fetchone()
            if provider_row is None:
                return False
            lock_resource(connection, "social-provider-targets", provider_row['provider'])
            current = connection.execute("SELECT provider,wake_revision,lease_until FROM social_targets WHERE id=%s AND lease_owner=%s FOR UPDATE", (target_id, owner)).fetchone()
            now = int(time.time())
            if not current or current['lease_until'] is None or current['lease_until'] <= now:
                return False
            if observed_wake_revision is not None and current['wake_revision'] > observed_wake_revision:
                next_check_at = 0
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
            current = connection.execute("SELECT lease_until FROM social_targets WHERE id=%s AND lease_owner=%s FOR UPDATE", (target_id, owner)).fetchone()
            now = int(time.time())
            if not current or current['lease_until'] is None or current['lease_until'] <= now:
                return False
            result = connection.execute("DELETE FROM social_targets WHERE id=%s AND lease_owner=%s AND lease_until>%s AND NOT EXISTS(SELECT 1 FROM social_subscriptions WHERE target_id=%s)", (target_id, owner, now, target_id))
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

    def save_social_connection(self, guild_id: int, provider: str, account_id: str, account_name: str, access_token_encrypted: str, refresh_token_encrypted: str | None, expires_at: int | None, *, _conn=None) -> None:
        now = int(time.time())
        with (nullcontext(_conn) if _conn is not None else self._connection()) as connection:
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

    def update_social_delivery(self, subscription_id: int, event_key: str, message_id: int | None, state: str = "sent") -> None:
        with self._connection() as connection:
            connection.execute("UPDATE social_deliveries SET discord_message_id=%s,state=%s,updated_at=%s WHERE subscription_id=%s AND event_key=%s", (message_id, state, int(time.time()), subscription_id, event_key))

    def begin_social_delivery_attempt(self, subscription_id: int, event_key: str) -> bool:
        with self._connection() as connection:
            row = connection.execute('SELECT state,attempts FROM social_deliveries WHERE subscription_id=%s AND event_key=%s FOR UPDATE',
                (subscription_id, event_key)).fetchone()
            if row is None or row['state'] in {'sent', 'failed', 'skipped'}:
                return False
            if row['attempts'] >= QUEUE_SPECS['social_events'].max_attempts:
                connection.execute("UPDATE social_deliveries SET state='failed',last_error='Delivery retry limit reached',updated_at=%s WHERE subscription_id=%s AND event_key=%s",
                    (int(time.time()), subscription_id, event_key))
                return False
            connection.execute('UPDATE social_deliveries SET attempts=attempts+1 WHERE subscription_id=%s AND event_key=%s',
                (subscription_id, event_key))
            return True

    def fail_social_delivery(self, subscription_id: int, event_key: str, error: str, *, retry: bool, uncertain: bool = False, attempted: bool = False) -> None:
        now = int(time.time())
        with self._connection() as connection:
            row = connection.execute("SELECT attempts FROM social_deliveries WHERE subscription_id=%s AND event_key=%s FOR UPDATE", (subscription_id, event_key)).fetchone()
            attempts = int(row["attempts"] if row else 0) + (0 if attempted else 1)
            exhausted = attempts >= QUEUE_SPECS['social_events'].max_attempts
            delay = min(3600, 15 * (2 ** min(attempts, 8))) if retry else 0
            connection.execute("""UPDATE social_deliveries SET state=%s,attempts=%s,next_attempt_at=%s,last_error=%s,updated_at=%s
                WHERE subscription_id=%s AND event_key=%s""", ("failed" if exhausted else "uncertain" if uncertain else "retry" if retry else "failed", attempts, now + delay, error[:500], now, subscription_id, event_key))

    def purge_social_history(self, *, retention_days: int = 30) -> int:
        cutoff = int(time.time()) - max(1, retention_days) * 86400
        with self._connection() as connection:
            event_count = connection.execute("DELETE FROM social_events WHERE processed_at IS NOT NULL AND processed_at<%s", (cutoff,)).rowcount
            # A retained event can resume after a long guild pause. Its terminal
            # receipts remain the deduplication and suppression record until the
            # event itself is gone, including when the queue's purge removed it.
            delivery_count = connection.execute("""DELETE FROM social_deliveries d
                WHERE updated_at<%s AND state IN ('sent','failed','skipped')
                AND NOT EXISTS(SELECT 1 FROM social_events e WHERE e.event_key=d.event_key)""", (cutoff,)).rowcount
        return int(delivery_count + event_count)

    def set_social_live_message(self, subscription_id: int, provider: str, account_id: str, channel_id: int, message_id: int,
                                *, event_key: str | None = None) -> None:
        with self._connection() as connection:
            lock_resource(connection, 'social-live-message', subscription_id)
            if event_key is not None:
                delivery = connection.execute('SELECT id FROM social_deliveries WHERE subscription_id=%s AND event_key=%s',
                                              (subscription_id, event_key)).fetchone()
                if delivery is None:
                    return
                newer = connection.execute("""SELECT 1 FROM social_deliveries WHERE subscription_id=%s
                    AND event_key LIKE %s AND state='sent' AND id>%s LIMIT 1""",
                    (subscription_id, provider + ':live_start:%', delivery['id'])).fetchone()
                ended = connection.execute("""SELECT 1 FROM social_deliveries WHERE subscription_id=%s
                    AND event_key LIKE %s AND state='sent' AND
                    (event_key=%s OR (discord_channel_id=%s AND discord_message_id=%s)) LIMIT 1""",
                    (subscription_id, provider + ':live_end:%', event_key.replace(':live_start:', ':live_end:', 1),
                     channel_id, message_id)).fetchone()
                if newer or ended:
                    return
            connection.execute("INSERT INTO social_live_messages(subscription_id,provider,account_id,discord_channel_id,discord_message_id) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(subscription_id,provider,account_id) DO UPDATE SET discord_channel_id=excluded.discord_channel_id,discord_message_id=excluded.discord_message_id", (subscription_id, provider, account_id, channel_id, message_id))

    def social_live_message(self, subscription_id: int, provider: str, account_id: str) -> dict[str, int] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT discord_channel_id,discord_message_id FROM social_live_messages WHERE subscription_id=%s AND provider=%s AND account_id=%s", (subscription_id, provider, account_id)).fetchone()
        return dict(row) if row else None

    def clear_social_live_message(self, subscription_id: int, provider: str, account_id: str,
                                  *, channel_id: int | None = None, message_id: int | None = None) -> None:
        with self._connection() as connection:
            lock_resource(connection, 'social-live-message', subscription_id)
            connection.execute("""DELETE FROM social_live_messages WHERE subscription_id=%s AND provider=%s AND account_id=%s
                AND (%s::bigint IS NULL OR discord_channel_id=%s) AND (%s::bigint IS NULL OR discord_message_id=%s)""",
                (subscription_id, provider, account_id, channel_id, channel_id, message_id, message_id))
