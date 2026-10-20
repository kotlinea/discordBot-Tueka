"""Deadline lock waits and late external edits must preserve campaign truth."""
import asyncio
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

from db_support import prepare_database
from database import lock_resource, transaction
from discord_io import DiscordFailure
from giveaways.repository import GiveawayRepository
from giveaways.service import GiveawayService
from jobs import LostLease, Outcome, run_batch
from test_giveaway_service import GeneratedPort


class GiveawayReviewBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.url = prepare_database('giveaway-review-' + uuid.uuid4().hex, self.addCleanup)
        self.now = 500000
        self.repo = GiveawayRepository(self.url, clock=lambda: self.now)
        self.repo.settings.set_module(1, 'giveaways', enabled=True)
        self.item = self.repo.create(1, 10, {'title': 'Boundary', 'channel_id': 20, 'ends_at': self.now + 60}, 'boundary')
        self.item = self.repo.launch(1, self.item['id'], 10, self.item['revision'])
        self.port = GeneratedPort()
        self.service = GiveawayService(self.repo, self.port)
        claim = self.repo.jobs.claim('initial-publication')
        self.assertIsNone((await self.service.publish(claim.payload)).error)
        self.assertTrue(self.repo.jobs.finish(claim, Outcome()))

    def blocked_entry_at_deadline(self, *, join):
        reached = threading.Event()
        def observed(connection, namespace, key):
            if threading.current_thread().name.startswith('giveaway-waiter') and namespace == 'guild-module':
                reached.set()
            return lock_resource(connection, namespace, key)
        with ThreadPoolExecutor(1, thread_name_prefix='giveaway-waiter') as executor:
            with patch('giveaways.repository.lock_resource', observed):
                with transaction(self.url) as connection:
                    lock_resource(connection, 'guild-module', '1:giveaways')
                    pending = executor.submit(self.repo.enter, 1, self.item['id'], 30, 100, 301, join=join)
                    self.assertTrue(reached.wait(5))
                    self.now = self.item['ends_at']
                with self.assertRaisesRegex(RuntimeError, 'campaign_not_accepting'):
                    pending.result(timeout=10)

    async def test_join_waiting_for_module_lock_is_rejected_at_deadline(self):
        self.blocked_entry_at_deadline(join=True)
        self.assertEqual(self.repo.history(1, self.item['id'])['entries'], [])

    async def test_leave_waiting_for_module_lock_is_rejected_at_deadline(self):
        self.repo.enter(1, self.item['id'], 30, 100, 300, join=True)
        self.blocked_entry_at_deadline(join=False)
        self.assertEqual(self.repo.history(1, self.item['id'])['entries'][0]['active'], 1)

    async def test_launch_waiting_for_module_lock_is_rejected_at_deadline(self):
        draft = self.repo.create(1, 10, {'title': 'Draft deadline', 'channel_id': 20, 'ends_at': self.now + 60}, 'draft-deadline')
        reached = threading.Event()
        def observed(connection, namespace, key):
            if threading.current_thread().name.startswith('launch-waiter') and namespace == 'guild-module':
                reached.set()
            return lock_resource(connection, namespace, key)
        with ThreadPoolExecutor(1, thread_name_prefix='launch-waiter') as executor:
            with patch('giveaways.repository.lock_resource', observed):
                with transaction(self.url) as connection:
                    lock_resource(connection, 'guild-module', '1:giveaways')
                    pending = executor.submit(self.repo.launch, 1, draft['id'], 10, draft['revision'])
                    self.assertTrue(reached.wait(5))
                    self.now = draft['ends_at']
                with self.assertRaisesRegex(RuntimeError, 'campaign_not_launchable'):
                    pending.result(timeout=10)
        self.assertEqual(self.repo.item(1, draft['id'])['status'], 'draft')

    async def finish_newer_deliveries(self):
        for owner in ('replacement', 'successor'):
            claim = self.repo.jobs.claim(owner)
            self.assertIsNotNone(claim)
            outcome = await self.service.publish(claim.payload)
            self.assertIsNone(outcome.error)
            self.assertTrue(self.repo.jobs.finish(claim, outcome))

    async def assert_durable_repair(self, external):
        repair = self.repo.jobs.claim('repair-after-old-external-completion')
        self.assertIsNotNone(repair, 'A late old edit must leave durable repair work')
        outcome = await self.service.publish(repair.payload)
        self.assertIsNone(outcome.error)
        self.assertTrue(self.repo.jobs.finish(repair, outcome))
        self.assertEqual(external['entrants'], 2)
        self.assertIsNone(self.repo.jobs.claim('empty'))

    async def test_expired_owner_late_edit_leaves_repair_without_finalizing_old_lease(self):
        self.repo.enter(1, self.item['id'], 30, 100, 300, join=True)
        claim = self.repo.jobs.claim('old-owner', lease_seconds=3)
        started, release = asyncio.Event(), asyncio.Event()
        external = {'entrants': 0}
        first_edit = True
        async def edit(plan, message, marker):
            nonlocal first_edit
            if first_edit:
                first_edit = False
                started.set()
                await release.wait()
            external['entrants'] = plan['entrants']
        self.port.edit = edit
        task = asyncio.create_task(self.service.publish(claim.payload), name='old-external-edit')
        try:
            await asyncio.wait_for(started.wait(), 5)
            self.repo.enter(1, self.item['id'], 31, 100, 310, join=True)
            self.now += 4
            await self.finish_newer_deliveries()
            release.set()
            with self.assertRaises(LostLease):
                await task
            self.assertFalse(self.repo.jobs.finish(claim, Outcome()))
            await self.assert_durable_repair(external)
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_runner_lease_loss_cannot_cancel_remote_edit_or_drop_its_repair(self):
        self.repo.enter(1, self.item['id'], 30, 100, 300, join=True)
        started, release, heartbeat, cancelled = (asyncio.Event() for _ in range(4))
        external = {'entrants': 0}
        first_edit = True
        async def edit(plan, message, marker):
            nonlocal first_edit
            if first_edit:
                first_edit = False
                started.set()
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    # The remote server already accepted the request. Cancelling
                    # our local wait cannot prevent its eventual side effect.
                    cancelled.set()
                    await release.wait()
            external['entrants'] = plan['entrants']
        self.port.edit = edit
        async def heartbeat_tick(_):
            await heartbeat.wait()
        class ObservedTask(asyncio.Task):
            def cancel(self, *args, **kwargs):
                if self.get_coro().__qualname__ == 'GiveawayService.publish':
                    cancelled.set()
                return super().cancel(*args, **kwargs)
        runner_asyncio = SimpleNamespace(create_task=ObservedTask, sleep=heartbeat_tick,
            wait=asyncio.wait, FIRST_COMPLETED=asyncio.FIRST_COMPLETED, CancelledError=asyncio.CancelledError)
        with patch('jobs.runner.asyncio', runner_asyncio):
            task = asyncio.create_task(run_batch(self.repo.jobs, 'old-runner', self.service.publish, limit=1, lease_seconds=3))
            try:
                await asyncio.wait_for(started.wait(), 5)
                self.repo.enter(1, self.item['id'], 31, 100, 310, join=True)
                self.now += 4
                await self.finish_newer_deliveries()
                heartbeat.set()
                await asyncio.wait_for(cancelled.wait(), 5)
                release.set()
                self.assertEqual(await asyncio.wait_for(task, 5), 0)
                await self.assert_durable_repair(external)
            finally:
                heartbeat.set()
                release.set()
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_late_edit_response_loss_also_reserves_repair(self):
        self.repo.enter(1, self.item['id'], 30, 100, 300, join=True)
        claim = self.repo.jobs.claim('old-response-loss', lease_seconds=3)
        started, release = asyncio.Event(), asyncio.Event()
        external = {'entrants': 0}
        first = True
        async def edit(plan, message, marker):
            nonlocal first
            late = first
            first = False
            if late:
                started.set()
                await release.wait()
            external['entrants'] = plan['entrants']
            if late:
                raise DiscordFailure('Delayed response lost', retry=True, partial=True)
        self.port.edit = edit
        task = asyncio.create_task(self.service.publish(claim.payload))
        try:
            await asyncio.wait_for(started.wait(), 5)
            self.repo.enter(1, self.item['id'], 31, 100, 310, join=True)
            self.now += 4
            await self.finish_newer_deliveries()
            release.set()
            self.assertTrue((await task).retry)
            self.assertFalse(self.repo.jobs.finish(claim, Outcome()))
            await self.assert_durable_repair(external)
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)

    async def test_repair_is_guild_scoped_idempotent_and_paused_while_off(self):
        self.repo.enter(1, self.item['id'], 30, 100, 300, join=True)
        claim = self.repo.jobs.claim('old', lease_seconds=3)
        self.now += 4
        replacement = self.repo.jobs.claim('replacement')
        self.assertTrue(self.repo.jobs.finish(replacement, Outcome()))
        self.repo.publication_repair(2, self.item['id'], claim.payload)
        self.assertIsNone(self.repo.jobs.claim('wrong-guild-did-not-queue'))
        self.repo.settings.set_module(1, 'giveaways', enabled=False)
        for _ in range(3):
            self.repo.publication_repair(1, self.item['id'], claim.payload)
        self.assertIsNone(self.repo.jobs.claim('paused'))
        self.repo.settings.set_module(1, 'giveaways', enabled=True)
        repair = self.repo.jobs.claim('only-repair')
        self.assertIsNotNone(repair)
        self.assertTrue(self.repo.jobs.finish(repair, Outcome()))
        self.assertIsNone(self.repo.jobs.claim('no-duplicate'))
