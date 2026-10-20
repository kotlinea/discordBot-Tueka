"""A newly successful recipient grants dispatch progress once across a crash."""
import time
import unittest
from unittest.mock import patch

from database import transaction
from db_support import snapshot
from jobs import Outcome
import test_social_pause_review as pause_fixture


class SocialSuccessCrashReviewTests(unittest.IsolatedAsyncioTestCase):
    setUp = pause_fixture.SocialPauseReviewTests.setUp
    subscription = pause_fixture.SocialPauseReviewTests.subscription
    event = pause_fixture.SocialPauseReviewTests.event
    state = pause_fixture.SocialPauseReviewTests.state

    async def successful_final_claim(self):
        active, paused = self.subscription(1), self.subscription(2)
        self.event(attempts=7)
        self.repository.record_social_delivery(active['id'], self.key, 11, None, 'retry')
        self.repository.record_social_delivery(paused['id'], self.key, 12, None, 'uncertain')
        self.settings.set_module(2, 'youtube_updates', enabled=False)
        with transaction(self.url) as c:
            c.execute('UPDATE social_deliveries SET attempts=7 WHERE subscription_id=%s', (active['id'],))
        now = [int(time.time())]
        queue = self.repository.event_jobs
        queue.clock = lambda: now[0]
        claim = queue.claim('crashing-owner', lease_seconds=10)
        self.assertEqual(claim.attempt, 8)
        outcome = await self.service.deliver_outcome(claim.payload)
        self.assertEqual(outcome.result, {'paused': True})
        receipt = self.repository.social_delivery(active['id'], self.key)
        self.assertEqual((receipt['state'], receipt['attempts']), ('sent', 8))
        self.assertEqual(receipt['dispatch_accounted_attempts'], 0)
        # Simulate death after the receipt commit, before Queue.finish.
        now[0] += 11
        before = snapshot(self.url)
        self.assertIsNone(queue.claim('still-disabled'))
        self.assertEqual(snapshot(self.url), before)
        self.settings.set_module(2, 'youtube_updates', enabled=True)
        return active, paused, now

    async def test_success_before_crash_preserves_other_guilds_resume(self):
        active, paused, _ = await self.successful_final_claim()
        queue = self.repository.event_jobs
        claim = queue.claim('resuming-owner')
        self.assertIsNotNone(claim, 'A fresh sent receipt must preserve the other recipient budget')
        self.assertEqual(self.repository.social_delivery(active['id'], self.key)['dispatch_accounted_attempts'], 8)
        outcome = await self.service.deliver_outcome(claim.payload)
        self.assertTrue(queue.finish(claim, outcome))
        self.assertEqual(self.repository.social_delivery(paused['id'], self.key)['state'], 'sent')
        self.assertEqual(self.port.calls, [(1, 11, False), (2, 12, True)])
        self.assertEqual(self.state()['status'], 'completed')

    async def test_success_progress_is_not_reused_for_permanent_dispatch_failure(self):
        active, paused, now = await self.successful_final_claim()
        queue = self.repository.event_jobs
        failures = []

        def fail_before_reservation(*args):
            failures.append(1)
            raise RuntimeError('Permanent dispatcher failure before recipient reservation')

        with patch.object(self.repository, 'begin_social_delivery_attempt', side_effect=fail_before_reservation):
            for _ in range(24):
                claim = queue.claim('failing-owner')
                if claim is None:
                    break
                try:
                    await self.service.deliver_outcome(claim.payload)
                except RuntimeError as exc:
                    self.assertTrue(queue.finish(claim, Outcome(str(exc), retry=True)))
                else:
                    self.fail('The enabled pending recipient must reach attempt reservation')
                now[0] += 4000
        self.assertEqual(len(failures), 8, 'Fresh successful progress grants exactly one dispatch budget')
        self.assertEqual(self.repository.social_delivery(active['id'], self.key)['dispatch_accounted_attempts'], 8)
        self.assertEqual(self.repository.social_delivery(paused['id'], self.key)['attempts'], 0)
        self.assertEqual(self.state()['status'], 'failed')
        self.assertIsNone(queue.claim('after-exhaustion'))
        self.assertEqual(self.port.calls, [(1, 11, False)])
