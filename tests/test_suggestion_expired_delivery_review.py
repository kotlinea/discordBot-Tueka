"""Late Discord effects reserve repair without granting an expired owner authority."""
import asyncio
import unittest
from jobs import LostLease, Outcome
from discord_io import DiscordFailure
from suggestions.delivery import SuggestionDeliveryService
import test_suggestion_review_boundaries
import test_suggestion_delivery

class ExpiredSuggestionEditTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_suggestion_review_boundaries.SyncOrderingTests.asyncSetUp

    async def test_late_old_lease_edit_must_reserve_current_card(self):
        await self.late_edit('success')

    async def test_cancelled_old_edit_waits_for_effect_before_reserving_repair(self):
        await self.late_edit('cancel')

    async def test_lost_response_after_old_edit_reserves_repair(self):
        await self.late_edit('response_lost')

    async def test_live_final_failure_does_not_resurrect_queue(self):
        with self.repo._connection() as c:
            c.execute('UPDATE suggestion_outbox SET attempts=7,lease_until=0 WHERE id=%s', (self.claim.id,))
        claim = self.repo.outbox_jobs.claim('final-owner')
        self.assertEqual(claim.attempt, 8)
        class Port:
            async def sync(self, item, settings):
                raise DiscordFailure('Generated persistent 500', retry=True)
        delivery = SuggestionDeliveryService(self.repo, self.settings, Port())
        result = await delivery.deliver(claim.payload)
        self.assertTrue(self.repo.outbox_jobs.finish(claim, result))
        with self.repo._connection() as c:
            failed = c.execute('SELECT status,attempts FROM suggestion_outbox WHERE id=%s', (claim.id,)).fetchone()
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(failed['attempts'], 8)
        self.assertIsNone(self.repo.outbox_jobs.claim('unexpected-replacement'),
                          'Live final failure created replacement job and reset retry budget')

    async def late_edit(self, mode):
        entered, release = asyncio.Event(), asyncio.Event()
        rendered = {'status': None}
        first = True
        waiting = None
        class Port:
            async def sync(inner, item, settings):
                nonlocal first, waiting
                initial = first
                if initial:
                    first = False
                    waiting = asyncio.current_task()
                    entered.set()
                    await release.wait()
                rendered['status'] = item['status']
                if initial and mode == 'response_lost':
                    raise DiscordFailure('Generated lost response', retry=True, partial=True)
        delivery = SuggestionDeliveryService(self.repo, self.settings, Port())
        old = asyncio.create_task(delivery.deliver(self.claim.payload))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            with self.repo._connection() as c:
                c.execute('UPDATE suggestion_outbox SET lease_until=0 WHERE id=%s', (self.claim.id,))
            current = self.repo.get(1, self.item['id'])
            self.repo.review(1, self.item['id'], 30, 'approved', 'Generated approval', expected_revision=current['revision'])
            async def drain():
                for _ in range(20):
                    claim = self.repo.outbox_jobs.claim('new-owner')
                    if claim is None:
                        return
                    result = await delivery.deliver(claim.payload)
                    self.assertIsNone(result.error)
                    self.assertTrue(self.repo.outbox_jobs.finish(claim, result))
                self.fail('queue did not drain')
            await drain()
            self.assertEqual(rendered['status'], 'approved')
            if mode == 'cancel':
                old.cancel()
                # Cancellation is delivered at the shield, while the external
                # operation remains pending until our explicit release.
                await asyncio.wait_for(asyncio.shield(asyncio.create_task(self.assert_operation_alive(waiting))), 5)
            release.set()
            try:
                await old
            except (LostLease, asyncio.CancelledError):
                pass
            await drain()
            self.assertEqual(self.repo.get(1, self.item['id'])['status'], 'approved')
            self.assertEqual(rendered['status'], 'approved', 'old expired edit overwrote approved card after queue drained')
        finally:
            release.set()
            if not old.done():
                try:
                    await old
                except (LostLease, asyncio.CancelledError):
                    pass

    async def assert_operation_alive(self, task):
        self.assertFalse(task.done())
        self.assertFalse(task.cancelled())

    async def test_repair_coalesces_and_respects_guild_retention_and_off(self):
        repo, job = self.repo, self.claim.payload
        with repo._connection() as c:
            c.execute('UPDATE suggestion_outbox SET lease_until=0 WHERE id=%s', (self.claim.id,))
        repo.delivery_repair(2, self.item['id'], job)
        with repo._connection() as c:
            self.assertEqual(c.execute("SELECT count(*) AS n FROM suggestion_outbox WHERE status='pending'").fetchone()['n'], 0)
        self.settings.set_module(1, 'suggestions', enabled=False)
        repo.delivery_repair(1, self.item['id'], job)
        repo.delivery_repair(1, self.item['id'], job)
        self.assertIsNone(repo.outbox_jobs.claim('off-worker'))
        with repo._connection() as c:
            self.assertEqual(c.execute("SELECT count(*) AS n FROM suggestion_outbox WHERE action='sync' AND status='pending'").fetchone()['n'], 1)
            c.execute('UPDATE suggestions SET expires_at=1 WHERE id=%s', (self.item['id'],))
            before = c.execute('SELECT count(*) AS n FROM suggestion_outbox').fetchone()['n']
        repo.delivery_repair(1, self.item['id'], job)
        with repo._connection() as c:
            self.assertEqual(c.execute('SELECT count(*) AS n FROM suggestion_outbox').fetchone()['n'], before)


class ExpiredSuggestionSendTests(unittest.IsolatedAsyncioTestCase):
    setUp = test_suggestion_delivery.SuggestionDeliveryTests.setUp

    async def test_cancelled_publish_repairs_only_by_receipt_reconciliation(self):
        entered, release = asyncio.Event(), asyncio.Event()
        sent, receipt, recoveries = 0, None, []
        class Port:
            async def publish(inner, item, settings, *, recover):
                nonlocal sent, receipt
                recoveries.append(recover)
                if recover:
                    return receipt
                sent += 1
                entered.set()
                await release.wait()
                receipt = 900
                return receipt
            async def sync(inner, item, settings):
                pass
        self.service.port = Port()
        claim = self.repo.outbox_jobs.claim('old-worker')
        task = asyncio.create_task(self.service.deliver(claim.payload))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            task.cancel()
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertIsNone(self.repo.get(1, self.item['id'])['message_id'])
            repair = self.repo.outbox_jobs.claim('repair-worker')
            self.assertNotEqual(repair.id, claim.id)
            self.assertTrue(repair.payload['payload']['recover'])
            result = await self.service.deliver(repair.payload)
            self.assertIsNone(result.error)
            self.assertTrue(self.repo.outbox_jobs.finish(repair, result))
            self.assertEqual(self.repo.get(1, self.item['id'])['message_id'], 900)
            self.assertEqual(sent, 1)
            self.assertEqual(recoveries, [False, True])
            with self.assertRaises(LostLease):
                with self.repo._connection() as c:
                    c.execute('UPDATE suggestion_outbox SET lease_until=0 WHERE id=%s', (claim.id,))
                self.repo.publication_delivered(claim.payload, 901)
        finally:
            release.set()
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
