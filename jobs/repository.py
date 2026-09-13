"""Transactional queue mechanics; domain tables retain their payloads."""
import json
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from database import require_current, transaction
from .models import Claim, Outcome


@dataclass(frozen=True)
class QueueSpec:
    table: str
    state: str = 'status'
    due: str = 'available_at'
    completed: str = 'completed_at'
    done: str = 'completed'
    result: str | None = None
    max_attempts: int = 8

    def __post_init__(self):
        for name in (self.table, self.state, self.due, self.completed, self.result):
            if name is not None and not re.fullmatch('[a-z_]+', name):
                raise ValueError('Invalid queue identifier')
        if self.max_attempts < 1 or self.done not in {'completed', 'done'}:
            raise ValueError('Invalid queue policy')


class QueueRepository:
    def __init__(self, database_path: str | Path, spec: QueueSpec, *, clock: Callable[[], float] = time.time):
        self.database_path = Path(database_path)
        require_current(self.database_path)
        self.spec, self.clock = spec, clock

    def claim(self, owner: str, *, lease_seconds: int = 60) -> Claim | None:
        if not owner or lease_seconds < 3:
            raise ValueError('Owner and a lease of at least three seconds are required')
        now, s = int(self.clock()), self.spec
        with transaction(self.database_path) as c:
            c.execute('BEGIN IMMEDIATE')
            # A crashed final attempt must terminate rather than remain stranded.
            c.execute(f"UPDATE {s.table} SET {s.state}='failed',{s.completed}=?,last_error='Lease expired at retry limit',lease_owner=NULL,lease_token=NULL,lease_until=NULL WHERE {s.state} IN ('pending','retry','processing') AND attempts>=? AND (lease_until IS NULL OR lease_until<=?)", (now, s.max_attempts, now))
            row = c.execute(f"SELECT * FROM {s.table} WHERE {s.state} IN ('pending','retry','processing') AND {s.due}<=? AND attempts<? AND (lease_until IS NULL OR lease_until<=?) ORDER BY {s.due},id LIMIT 1", (now, s.max_attempts, now)).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            c.execute(f"UPDATE {s.table} SET {s.state}='processing',lease_owner=?,lease_token=?,lease_until=?,attempts=attempts+1 WHERE id=?", (owner, token, now + lease_seconds, row['id']))
            payload = dict(row)
            for column in ('payload_json', 'options_json'):
                if column in payload:
                    payload[column.removesuffix('_json')] = json.loads(payload[column])
            return Claim(int(row['id']), owner, token, payload, int(row['attempts']) + 1)

    def renew(self, claim: Claim, *, lease_seconds: int = 60) -> bool:
        if lease_seconds < 3:
            raise ValueError('Lease must be at least three seconds')
        now, s = int(self.clock()), self.spec
        with transaction(self.database_path) as c:
            return c.execute(f"UPDATE {s.table} SET lease_until=? WHERE id=? AND lease_owner=? AND lease_token=? AND lease_until>? AND {s.state}='processing'", (now + lease_seconds, claim.id, claim.owner, claim.token, now)).rowcount == 1

    def finish(self, claim: Claim, outcome: Outcome) -> bool:
        now, s = int(self.clock()), self.spec
        retry = outcome.error is not None and outcome.retry and claim.attempt < s.max_attempts
        state = 'retry' if retry else ('failed' if outcome.error is not None else s.done)
        due = now + min(3600, 15 * 2 ** min(claim.attempt, 8))
        values = [state, None if retry else now, (outcome.error or '')[:500] or None, int(retry), due]
        result_sql = ''
        if s.result:
            result_sql = f',{s.result}=?'
            values.append(json.dumps(outcome.result, ensure_ascii=False) if outcome.result is not None else None)
        with transaction(self.database_path) as c:
            return c.execute(f"UPDATE {s.table} SET {s.state}=?,{s.completed}=?,last_error=?,{s.due}=CASE WHEN ? THEN ? ELSE {s.due} END{result_sql},lease_owner=NULL,lease_token=NULL,lease_until=NULL WHERE id=? AND lease_owner=? AND lease_token=? AND lease_until>? AND {s.state}='processing'", (*values, claim.id, claim.owner, claim.token, now)).rowcount == 1

    def purge(self, *, retention_seconds: int = 30 * 86400) -> int:
        if retention_seconds < 1:
            raise ValueError('Retention must be positive')
        s = self.spec
        with transaction(self.database_path) as c:
            return c.execute(f"DELETE FROM {s.table} WHERE {s.state} IN (?, 'failed') AND {s.completed}<? AND lease_owner IS NULL", (s.done, int(self.clock()) - retention_seconds)).rowcount
