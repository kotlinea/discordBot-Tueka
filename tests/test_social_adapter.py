import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from db_support import prepare_database
from discord_io import DiscordFailure
from guild_settings import GuildSettingsRepository
from social import SocialRepository
from social.models import default_templates
from social.service import SocialDeliveryService


class FakeSocialPort:
    def __init__(self):
        self.messages = {}
        self.created = 0

    def available(self, *args):
        return True

    async def send(self, guild_id, channel_id, content, embed, role_id, receipt_key, *, recover, created_at):
        if recover:
            if receipt_key not in self.messages:
                raise DiscordFailure('cannot reconcile', partial=True)
            return self.messages[receipt_key]
        self.created += 1
        self.messages[receipt_key] = self.created
        return self.created

    async def edit(self, *args):
        pass


class SocialAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = prepare_database(Path(self.temp.name) / 'test.db')
        self.repository = SocialRepository(path)
        self.settings = GuildSettingsRepository(path)
        self.settings.set_module(1, 'twitch_updates', enabled=True)
        self.subscription = self.repository.save_social_subscription_v2(1, 'twitch', 'creator', 10,
            ['live_start', 'live_end'], {}, default_templates('twitch'))
        self.port = FakeSocialPort()
        self.service = SocialDeliveryService(self.repository, self.settings, self.port)
        self.event = {'provider': 'twitch', 'account_id': 'creator', 'event_type': 'live_start',
                      'event_key': 'twitch:live_start:one', 'payload': {'account': 'creator'}}

    async def test_sent_message_is_recovered_after_database_failure_without_resending(self):
        with patch.object(self.repository, 'update_social_delivery', side_effect=RuntimeError('database unavailable')):
            with self.assertRaises(RuntimeError):
                await self.service.deliver(self.event)
        restarted = SocialDeliveryService(SocialRepository(self.repository.database_path), self.settings, self.port)
        self.assertTrue(await restarted.deliver(self.event))
        self.assertEqual(self.port.created, 1)
        delivery = self.repository.social_delivery(self.subscription['id'], self.event['event_key'])
        self.assertEqual(delivery['state'], 'sent')
        self.assertEqual(delivery['discord_message_id'], 1)

    async def test_missing_receipt_does_not_create_a_duplicate(self):
        self.repository.record_social_delivery(self.subscription['id'], self.event['event_key'], 10, None, 'pending')
        self.assertFalse(await self.service.deliver(self.event))
        self.assertEqual(self.port.created, 0)
        self.assertEqual(self.repository.social_delivery(self.subscription['id'], self.event['event_key'])['state'], 'uncertain')

    async def test_live_reference_write_is_repaired_after_delivery_commit(self):
        with patch.object(self.repository, 'set_social_live_message', side_effect=RuntimeError('database unavailable')):
            with self.assertRaises(RuntimeError):
                await self.service.deliver(self.event)
        self.assertTrue(await self.service.deliver(self.event))
        self.assertEqual(self.port.created, 1)
        self.assertEqual(self.repository.social_live_message(self.subscription['id'], 'twitch', 'creator')['discord_message_id'], 1)
