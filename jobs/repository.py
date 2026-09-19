"""Transactional queue mechanics; domain tables retain their payloads."""
import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from database import require_current, transaction
from .models import Claim, Outcome, LostLease
from observability.metrics import registry


@dataclass(frozen=True)
class QueueSpec:
    table: str
    state: str = 'status'
    due: str = 'available_at'
    completed: str = 'completed_at'
    done: str = 'completed'
    result: str | None = None
    max_attempts: int = 8
    created: str | None = 'created_at'

    def __post_init__(self):
        for name in (self.table, self.state, self.due, self.completed, self.result, self.created):
            if name is not None and not re.fullmatch('[a-z_]+', name):
                raise ValueError('Invalid queue identifier')
        if self.max_attempts < 1 or self.done not in {'completed', 'done'}:
            raise ValueError('Invalid queue policy')


class QueueRepository:
    def __init__(self, database_url: str, spec: QueueSpec, *, clock: Callable[[], float] = time.time):
        self.database_url = database_url
        require_current(self.database_url)
        self.spec, self.clock = spec, clock

    def claim(self, owner: str, *, lease_seconds: int = 60) -> Claim | None:
        if not owner or lease_seconds < 3:
            raise ValueError('Owner and a lease of at least three seconds are required')
        now, s = int(self.clock()), self.spec
        with transaction(self.database_url) as c:
            # A crashed final attempt must terminate rather than remain stranded.
            c.execute(f"UPDATE {s.table} SET {s.state}='failed',{s.completed}=%s,last_error='Lease expired at retry limit',lease_owner=NULL,lease_token=NULL,lease_until=NULL WHERE id IN (SELECT id FROM {s.table} WHERE {s.state} IN ('pending','retry','processing') AND attempts>=%s AND (lease_until IS NULL OR lease_until<=%s) FOR UPDATE SKIP LOCKED)", (now, s.max_attempts, now))
            row = c.execute(f"SELECT * FROM {s.table} WHERE {s.state} IN ('pending','retry','processing') AND {s.due}<=%s AND attempts<%s AND (lease_until IS NULL OR lease_until<=%s) ORDER BY {s.due},id LIMIT 1 FOR UPDATE SKIP LOCKED", (now, s.max_attempts, now)).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            c.execute(f"UPDATE {s.table} SET {s.state}='processing',lease_owner=%s,lease_token=%s,lease_until=%s,attempts=attempts+1 WHERE id=%s", (owner, token, now + lease_seconds, row['id']))
            payload = dict(row)
            payload['_lease'] = {'owner': owner, 'token': token}
            for column in ('payload_json', 'options_json'):
                if column in payload:
                    payload[column.removesuffix('_json')] = json.loads(payload[column])
            return Claim(int(row['id']), owner, token, payload, int(row['attempts']) + 1)

    def renew(self, claim: Claim, *, lease_seconds: int = 60) -> bool:
        if lease_seconds < 3:
            raise ValueError('Lease must be at least three seconds')
        now, s = int(self.clock()), self.spec
        with transaction(self.database_url) as c:
            return c.execute(f"UPDATE {s.table} SET lease_until=%s WHERE id=%s AND lease_owner=%s AND lease_token=%s AND lease_until>%s AND {s.state}='processing'", (now + lease_seconds, claim.id, claim.owner, claim.token, now)).rowcount == 1

    def finish(self, claim: Claim, outcome: Outcome) -> bool:
        now, s = int(self.clock()), self.spec
        retry = outcome.error is not None and outcome.retry and claim.attempt < s.max_attempts
        state = 'retry' if retry else ('failed' if outcome.error is not None else s.done)
        due = now + min(3600, 15 * 2 ** min(claim.attempt, 8))
        values = [state, None if retry else now, (outcome.error or '')[:500] or None, retry, due]
        result_sql = ''
        if s.result:
            result_sql = f',{s.result}=%s'
            values.append(json.dumps(outcome.result, ensure_ascii=False) if outcome.result is not None else None)
        with transaction(self.database_url) as c:
            changed = c.execute(f"UPDATE {s.table} SET {s.state}=%s,{s.completed}=%s,last_error=%s,{s.due}=CASE WHEN %s THEN %s ELSE {s.due} END{result_sql},lease_owner=NULL,lease_token=NULL,lease_until=NULL WHERE id=%s AND lease_owner=%s AND lease_token=%s AND lease_until>%s AND {s.state}='processing'", (*values, claim.id, claim.owner, claim.token, now)).rowcount == 1
        if changed:
            registry.add('job_results_total', queue=s.table, outcome=state)
        return changed

    def purge(self, *, retention_seconds: int = 30 * 86400) -> int:
        if retention_seconds < 1:
            raise ValueError('Retention must be positive')
        s = self.spec
        with transaction(self.database_url) as c:
            return c.execute(f"DELETE FROM {s.table} WHERE {s.state} IN (%s, 'failed') AND {s.completed}<%s AND lease_owner IS NULL", (s.done, int(self.clock()) - retention_seconds)).rowcount


class ResourceLeaseRepository:
    def __init__(self, database, namespace, key, *, seconds=60, clock=time.time):
        if seconds < 3:
            raise ValueError('Lease must last at least three seconds')
        self.database, self.namespace, self.key = database, namespace, str(key)
        self.seconds, self.clock, self.token = seconds, clock, uuid.uuid4().hex

    def acquire(self):
        with transaction(self.database) as c:
            changed = c.execute('''INSERT INTO resource_leases VALUES(%s,%s,%s,%s)
                ON CONFLICT(namespace,resource_key) DO UPDATE SET token=excluded.token,lease_until=excluded.lease_until
                WHERE resource_leases.lease_until<=%s''',
                (self.namespace, self.key, self.token, int(self.clock()) + self.seconds, int(self.clock())))
            if changed.rowcount != 1:
                raise LostLease('Resource operation already owned')

    def guard(self, connection):
        owned = connection.execute('''SELECT 1 FROM resource_leases
            WHERE namespace=%s AND resource_key=%s AND token=%s AND lease_until>%s FOR UPDATE''',
            (self.namespace, self.key, self.token, int(self.clock()))).fetchone()
        if not owned:
            raise LostLease('Resource operation ownership expired or changed')

    def renew(self):
        with transaction(self.database) as c:
            self.guard(c)
            c.execute('UPDATE resource_leases SET lease_until=%s WHERE namespace=%s AND resource_key=%s AND token=%s',
                (int(self.clock()) + self.seconds, self.namespace, self.key, self.token))

    def release(self):
        with transaction(self.database) as c:
            c.execute('DELETE FROM resource_leases WHERE namespace=%s AND resource_key=%s AND token=%s',
                      (self.namespace, self.key, self.token))

    def check(self):
        with transaction(self.database) as c:
            self.guard(c)
