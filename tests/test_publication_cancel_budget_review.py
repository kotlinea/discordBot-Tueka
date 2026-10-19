"""A cancelled final attempt must retain repair after its accepted edit settles."""
import asyncio
import unittest

from database import transaction
from discord_io import DiscordFailure
import test_giveaway_review_boundaries
import test_starboard_review_boundaries


async def cancel_and_release(case, task, release):
    task.cancel('Generated final-attempt shutdown')
    barrier = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_soon(barrier.set_result, None)
    await barrier
    case.assertFalse(task.done(), 'Accepted edit must settle before cancellation')
    release.set()
    with case.assertRaises(asyncio.CancelledError):
        await asyncio.wait_for(task, 5)


class GiveawayFinalCancellationTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_giveaway_review_boundaries.GiveawayReviewBoundaryTests.asyncSetUp

    async def test_live_final_failure_keeps_retry_budget_bounded(self):
        self.repo.enter(1, self.item['id'], 30, 100, 300, join=True)
        with transaction(self.url) as c:
            c.execute("UPDATE giveaway_outbox SET attempts=7 WHERE status='pending'")
        claim = self.repo.jobs.claim('ordinary-final-failure')
        self.assertEqual(claim.attempt, 8)

        async def failure(*args):
            raise DiscordFailure('Generated persistent failure', retry=True)

        self.port.edit = failure
        outcome = await self.service.publish(claim.payload)
        self.assertTrue(outcome.retry)
        self.assertTrue(self.repo.jobs.finish(claim, outcome))
        self.now += 61
        self.assertIsNone(self.repo.jobs.claim('must-not-reset-budget'))
        with transaction(self.url) as c:
            row = c.execute('SELECT status,attempts FROM giveaway_outbox WHERE id=%s', (claim.id,)).fetchone()
        self.assertEqual((row['status'], row['attempts']), ('failed', 8))

    async def test_final_cancelled_edit_retains_current_campaign_repair(self):
        self.repo.enter(1, self.item['id'], 30, 100, 300, join=True)
        with transaction(self.url) as c:
            c.execute("UPDATE giveaway_outbox SET attempts=7 WHERE status='pending'")
        claim = self.repo.jobs.claim('final-cancelled', lease_seconds=60)
        self.assertEqual(claim.attempt, 8)
        entered, release = asyncio.Event(), asyncio.Event()
        rendered = {'entrants': None}
        first = True

        async def edit(plan, message, marker):
            nonlocal first
            old = first
            first = False
            if old:
                entered.set()
                await release.wait()
            rendered['entrants'] = plan['entrants']

        self.port.edit = edit
        task = asyncio.create_task(self.service.publish(claim.payload))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            self.repo.enter(1, self.item['id'], 31, 100, 310, join=True)
            successor = self.repo.jobs.claim('newer-publication')
            self.assertIsNotNone(successor)
            outcome = await self.service.publish(successor.payload)
            self.assertIsNone(outcome.error)
            self.assertTrue(self.repo.jobs.finish(successor, outcome))
            self.assertEqual(rendered['entrants'], 2)
            await cancel_and_release(self, task, release)
            self.assertEqual(rendered['entrants'], 1)
            self.now += 61
            repair = self.repo.jobs.claim('after-final-expiry')
            self.assertIsNotNone(repair, 'Cancelled final attempt dropped late-edit repair')
            outcome = await self.service.publish(repair.payload)
            self.assertIsNone(outcome.error)
            self.assertTrue(self.repo.jobs.finish(repair, outcome))
            self.assertEqual(rendered['entrants'], 2)
            self.assertIsNone(self.repo.jobs.claim('drained'))
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)


class StarboardFinalCancellationTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_starboard_review_boundaries.StarboardReviewBoundaryTests.asyncSetUp

    async def test_live_final_failure_keeps_retry_budget_bounded(self):
        initial = self.repo.jobs.claim('initial-publication')
        outcome = await self.delivery.handle(initial.payload)
        self.assertIsNone(outcome.error)
        self.assertTrue(self.repo.jobs.finish(initial, outcome))
        self.adapter.value = {**self.source, 'content': 'Changed snapshot'}
        self.repo.observe(1, self.board['id'], 1, self.adapter.value, 2)
        with transaction(self.url) as c:
            c.execute("UPDATE starboard_outbox SET attempts=7 WHERE status='pending'")
        claim = self.repo.jobs.claim('ordinary-final-failure')
        self.assertEqual(claim.attempt, 8)

        async def failure(*args):
            raise DiscordFailure('Generated persistent failure', retry=True)

        self.adapter.edit = failure
        outcome = await self.delivery.handle(claim.payload)
        self.assertTrue(outcome.retry)
        self.assertTrue(self.repo.jobs.finish(claim, outcome))
        self.now += 61
        self.assertIsNone(self.repo.jobs.claim('must-not-reset-budget'))
        with transaction(self.url) as c:
            row = c.execute('SELECT status,attempts FROM starboard_outbox WHERE id=%s', (claim.id,)).fetchone()
        self.assertEqual((row['status'], row['attempts']), ('failed', 8))

    async def test_final_cancelled_edit_retains_current_source_repair(self):
        initial = self.repo.jobs.claim('initial-publication')
        outcome = await self.delivery.handle(initial.payload)
        self.assertIsNone(outcome.error)
        self.assertTrue(self.repo.jobs.finish(initial, outcome))
        self.adapter.value = {**self.source, 'content': 'Old snapshot'}
        self.repo.observe(1, self.board['id'], 1, self.adapter.value, 2)
        with transaction(self.url) as c:
            c.execute("UPDATE starboard_outbox SET attempts=7 WHERE status='pending'")
        claim = self.repo.jobs.claim('final-cancelled', lease_seconds=60)
        self.assertEqual(claim.attempt, 8)
        entered, release = asyncio.Event(), asyncio.Event()
        rendered = {'content': None}
        first = True

        async def edit(guild, channel, message, source, score, emoji, marker):
            nonlocal first
            old = first
            first = False
            if old:
                entered.set()
                await release.wait()
            rendered['content'] = source['content']

        self.adapter.edit = edit
        task = asyncio.create_task(self.delivery.handle(claim.payload))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            self.adapter.value = {**self.source, 'content': 'Current snapshot'}
            self.repo.observe(1, self.board['id'], 1, self.adapter.value, 2)
            successor = self.repo.jobs.claim('newer-publication')
            self.assertIsNotNone(successor)
            outcome = await self.delivery.handle(successor.payload)
            self.assertIsNone(outcome.error)
            self.assertTrue(self.repo.jobs.finish(successor, outcome))
            self.assertEqual(rendered['content'], 'Current snapshot')
            await cancel_and_release(self, task, release)
            self.assertEqual(rendered['content'], 'Old snapshot')
            self.now += 61
            repair = self.repo.jobs.claim('after-final-expiry')
            self.assertIsNotNone(repair, 'Cancelled final attempt dropped late-edit repair')
            outcome = await self.delivery.handle(repair.payload)
            self.assertIsNone(outcome.error)
            self.assertTrue(self.repo.jobs.finish(repair, outcome))
            self.assertEqual(rendered['content'], 'Current snapshot')
            self.assertIsNone(self.repo.jobs.claim('drained'))
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
