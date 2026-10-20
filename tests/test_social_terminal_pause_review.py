"""Fresh terminal progress survives its recipient's later guild pause."""
import unittest

import test_social_success_crash_review as success_fixture


class SocialTerminalPauseReviewTests(unittest.IsolatedAsyncioTestCase):
    setUp = success_fixture.SocialSuccessCrashReviewTests.setUp
    subscription = success_fixture.SocialSuccessCrashReviewTests.subscription
    event = success_fixture.SocialSuccessCrashReviewTests.event
    state = success_fixture.SocialSuccessCrashReviewTests.state
    successful_final_claim = success_fixture.SocialSuccessCrashReviewTests.successful_final_claim

    async def test_success_progress_survives_successful_guild_being_disabled(self):
        active, paused, _ = await self.successful_final_claim()
        self.settings.set_module(1, 'youtube_updates', enabled=False)

        queue = self.repository.event_jobs
        claim = queue.claim('resuming-other-guild')
        self.assertIsNotNone(claim, 'Fresh successful progress must survive its guild being disabled')
        self.assertEqual(self.repository.social_delivery(active['id'], self.key)['dispatch_accounted_attempts'], 8)

        outcome = await self.service.deliver_outcome(claim.payload)
        self.assertTrue(queue.finish(claim, outcome))
        self.assertEqual(self.repository.social_delivery(paused['id'], self.key)['state'], 'sent')
        self.assertEqual(self.port.calls, [(1, 11, False), (2, 12, True)])
        self.assertEqual(self.state()['status'], 'completed')
