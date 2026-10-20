"""Pausing during channel availability checking preserves an existing intent."""
import unittest

from database import transaction
from social.models import default_templates
from social.service import SocialDeliveryService
import test_social_pause_review as pause_fixture


class PauseDuringAvailabilityPort:
    def __init__(self, settings):
        self.settings = settings
        self.available_calls = []

    def available(self, guild_id, channel_id):
        self.available_calls.append((guild_id, channel_id))
        self.settings.set_module(guild_id, 'youtube_updates', enabled=False)
        return False

    async def send(self, *args, **kwargs):
        raise AssertionError('A paused intent must not send')

    async def edit(self, *args, **kwargs):
        raise AssertionError('A paused intent must not edit')


class SocialPauseToggleReviewTests(unittest.IsolatedAsyncioTestCase):
    setUp = pause_fixture.SocialPauseReviewTests.setUp

    async def assert_pause_preserves_receipt(self, event_type, state, message_id):
        account_id = f'creator-{state}'
        subscription = self.repository.save_social_subscription_v2(
            1, 'youtube', account_id, 11, [event_type], {}, default_templates('youtube'))
        self.settings.set_module(1, 'youtube_updates', enabled=True)
        event_key = f'youtube:{event_type}:pause-during-availability-{state}'
        self.repository.record_social_delivery(subscription['id'], event_key, 11, message_id, state)
        with transaction(self.url) as connection:
            connection.execute('''UPDATE social_deliveries SET attempts=2,
                next_attempt_at=0,last_error='existing retry error'
                WHERE subscription_id=%s AND event_key=%s''', (subscription['id'], event_key))
        before = self.repository.social_delivery(subscription['id'], event_key)
        port = PauseDuringAvailabilityPort(self.settings)
        service = SocialDeliveryService(self.repository, self.settings, port)

        outcome = await service.deliver_outcome({
            'provider': 'youtube', 'account_id': account_id, 'event_type': event_type,
            'event_key': event_key, 'payload': {'account': 'creator'},
        })

        self.assertEqual(port.available_calls, [(1, 11)])
        self.assertFalse(self.settings.module_enabled(1, 'youtube_updates'))
        with self.subTest(check='receipt preserved'):
            self.assertEqual(self.repository.social_delivery(subscription['id'], event_key), before)
        with self.subTest(check='paused outcome'):
            self.assertIsNone(outcome.error)
            self.assertEqual(outcome.result, {'paused': True})

    async def test_send_intent_paused_during_availability_preserves_retry_and_uncertain(self):
        for state in ('retry', 'uncertain'):
            with self.subTest(state=state):
                await self.assert_pause_preserves_receipt('video', state, None)

    async def test_live_end_edit_paused_during_availability_preserves_retry_and_uncertain(self):
        for state in ('retry', 'uncertain'):
            with self.subTest(state=state):
                await self.assert_pause_preserves_receipt('live_end', state, 901)
