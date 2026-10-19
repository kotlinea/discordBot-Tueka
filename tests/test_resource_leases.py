import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database import transaction
from db_support import prepare_database
from jobs import LostLease
from jobs.leases import ResourceLease


class ResourceLeaseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = prepare_database(Path(self.temp.name) / 'test.db', self.addCleanup)

    async def test_expired_owner_cannot_commit_renew_or_release_successor(self):
        now = 100
        first = ResourceLease(self.database, 'lockdown', 1, seconds=3, clock=lambda: now)
        second = ResourceLease(self.database, 'lockdown', 1, seconds=3, clock=lambda: now)
        first.acquire()
        with self.assertRaises(LostLease) as collision:
            second.acquire()
        self.assertEqual(str(collision.exception), 'Resource operation already owned')
        self.assertEqual(collision.exception.competing_owner_token, first.token)
        now = 103
        with self.assertRaises(LostLease):
            first.renew()
        second.acquire()
        self.assertEqual(collision.exception.competing_owner_token, first.token)
        with transaction(self.database) as connection:
            with self.assertRaises(LostLease):
                first.guard(connection)
            second.guard(connection)
        first.release()
        second.renew()
        second.release()

    async def test_lost_lease_legacy_construction_keeps_runtime_error_contract(self):
        failure = LostLease('ownership lost', 'detail')
        self.assertIsInstance(failure, RuntimeError)
        self.assertEqual(failure.args, ('ownership lost', 'detail'))
        self.assertIsNone(failure.competing_owner_token)

    async def test_cancellation_releases_ownership_and_cancels_external_operation(self):
        lease = ResourceLease(self.database, 'lockdown', 1)
        started, stopped = asyncio.Event(), asyncio.Event()

        async def operation(owned):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        task = asyncio.create_task(lease.run(operation))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(stopped.is_set())
        successor = ResourceLease(self.database, 'lockdown', 1)
        successor.acquire()
        successor.release()

    async def test_expiry_during_operation_rejects_success(self):
        now = 100
        lease = ResourceLease(self.database, 'lockdown', 1, seconds=3, clock=lambda: now)

        async def operation(owned):
            nonlocal now
            now = 104
            return 'must not succeed'

        with self.assertRaises(LostLease):
            await lease.run(operation)

    async def test_renewal_failure_cancels_inflight_operation(self):
        lease = ResourceLease(self.database, 'lockdown', 1, seconds=3)
        stopped = asyncio.Event()

        async def operation(owned):
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        with patch.object(lease, 'renew', side_effect=LostLease('taken over')):
            with self.assertRaises(LostLease):
                await asyncio.wait_for(lease.run(operation), timeout=5)
        self.assertTrue(stopped.is_set())
