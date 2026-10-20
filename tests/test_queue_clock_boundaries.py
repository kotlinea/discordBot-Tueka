"""Lease clocks are evaluated after database acquisition and row-lock waits."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from threading import Event
from unittest.mock import patch

from database import transaction
from database import connections
from database.testing import temporary_database
from jobs import LostLease, Outcome, QueueRepository, QueueSpec
from jobs.repository import ResourceLeaseRepository


class LeaseClockBoundaries(unittest.TestCase):
    def setUp(self):
        self.context = temporary_database()
        self.url = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)
        self.now = 100
        self.queue = QueueRepository(self.url, QueueSpec('ticket_outbox'), clock=lambda: self.now)
        with transaction(self.url) as c:
            c.execute("INSERT INTO ticket_outbox(ticket_id,action,actor_id,payload_json,available_at,created_at) VALUES(1,'reply',2,'{}',0,1)")

    def after_pool_wait(self, operation):
        requested = Event()
        real_pool = connections.pool(self.url)
        class RequestedPool:
            @contextmanager
            def connection(proxy):
                requested.set()
                with real_pool.connection() as c:
                    yield c
        with ExitStack() as slots, ThreadPoolExecutor(max_workers=1) as executor:
            for _ in range(4):
                slots.enter_context(real_pool.connection())
            with patch.object(connections, 'pool', return_value=RequestedPool()):
                future = executor.submit(operation)
                try:
                    self.assertTrue(requested.wait(5), 'pool acquisition was never requested')
                    self.now = 105
                finally:
                    slots.close()
                return future.result(timeout=10)

    def after_row_wait(self, table, operation, *, table_lock=False):
        requested = Event()
        class RequestedConnection:
            def __init__(proxy, connection):
                proxy.connection = connection
            def execute(proxy, query, *args, **kwargs):
                if table in str(query):
                    requested.set()
                return proxy.connection.execute(query, *args, **kwargs)
        real_transaction = transaction
        @contextmanager
        def gated_transaction(url):
            with real_transaction(url) as c:
                yield RequestedConnection(c)
        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction(self.url) as holder:
                holder.execute(f'LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE' if table_lock else f'SELECT * FROM {table} FOR UPDATE')
                with patch('jobs.repository.transaction', gated_transaction):
                    future = executor.submit(operation)
                    self.assertTrue(requested.wait(5), 'row access was never requested')
                    self.now = 105
            return future.result(timeout=10)

    def test_claim_creates_live_lease_after_pool_wait(self):
        claim = self.after_pool_wait(lambda: self.queue.claim('first', lease_seconds=3))
        with transaction(self.url) as c:
            expires = c.execute('SELECT lease_until FROM ticket_outbox WHERE id=%s', (claim.id,)).fetchone()['lease_until']
        self.assertEqual(expires, 108)
        self.assertIsNone(self.queue.claim('second', lease_seconds=3))

    def test_claim_creates_live_lease_after_cleanup_lock_wait(self):
        claim = self.after_row_wait('ticket_outbox', lambda: self.queue.claim('first', lease_seconds=3), table_lock=True)
        with transaction(self.url) as c:
            expires = c.execute('SELECT lease_until FROM ticket_outbox WHERE id=%s', (claim.id,)).fetchone()['lease_until']
        self.assertEqual(expires, 108)

    def test_finish_rejects_expiry_during_pool_wait(self):
        claim = self.queue.claim('first', lease_seconds=3)
        self.assertFalse(self.after_pool_wait(lambda: self.queue.finish(claim, Outcome())))
        self.assertIsNotNone(self.queue.claim('second'))

    def test_renew_rejects_expiry_during_pool_wait(self):
        claim = self.queue.claim('first', lease_seconds=3)
        self.assertFalse(self.after_pool_wait(lambda: self.queue.renew(claim)))

    def test_finish_rejects_expiry_during_row_lock_wait(self):
        claim = self.queue.claim('first', lease_seconds=3)
        self.assertFalse(self.after_row_wait('ticket_outbox', lambda: self.queue.finish(claim, Outcome())))

    def test_renew_rejects_expiry_during_row_lock_wait(self):
        claim = self.queue.claim('first', lease_seconds=3)
        self.assertFalse(self.after_row_wait('ticket_outbox', lambda: self.queue.renew(claim)))

    def resource(self):
        return ResourceLeaseRepository(self.url, 'clock-boundary', 'one', seconds=3, clock=lambda: self.now)

    def test_resource_guard_rejects_expiry_during_row_lock_wait(self):
        lease = self.resource()
        lease.acquire()
        def guarded():
            from jobs import repository
            with repository.transaction(self.url) as c:
                lease.guard(c)
        with self.assertRaises(LostLease):
            self.after_row_wait('resource_leases', guarded)

    def test_resource_renew_rejects_expiry_during_row_lock_wait(self):
        lease = self.resource()
        lease.acquire()
        with self.assertRaises(LostLease):
            self.after_row_wait('resource_leases', lease.renew)

    def test_resource_acquire_creates_live_lease_after_conflict_wait(self):
        first, successor = self.resource(), self.resource()
        first.acquire()
        self.now = 103
        self.after_row_wait('resource_leases', successor.acquire)
        with transaction(self.url) as c:
            row = c.execute('SELECT token,lease_until FROM resource_leases').fetchone()
        self.assertEqual(row['token'], successor.token)
        self.assertEqual(row['lease_until'], 108)

