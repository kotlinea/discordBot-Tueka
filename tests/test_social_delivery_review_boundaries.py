"""Delivery recovery must retain its original publication and destination."""
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


class PublicationPort:
    def __init__(self):
        self.messages = {}
        self.sends = []
        self.edits = []
        self.fail_edit = False
        self.on_edit = None
        self.on_send = None
        self.missing_edit = False
        self.unavailable = set()

    def available(self, guild_id, channel_id):
        return channel_id not in self.unavailable

    async def send(self, guild_id, channel_id, content, embed, role_id, receipt_key, *, recover, created_at):
        self.sends.append((channel_id, recover))
        key = (channel_id, receipt_key)
        if recover:
            if key not in self.messages:
                raise DiscordFailure('Receipt not found', partial=True)
            return self.messages[key]
        message_id = len(self.messages) + 1
        self.messages[key] = message_id
        if self.on_send:
            callback, self.on_send = self.on_send, None
            await callback()
        return message_id

    async def edit(self, guild_id, channel_id, message_id, embed):
        if self.missing_edit:
            self.missing_edit = False
            raise DiscordFailure('Message deleted', missing=True)
        if self.fail_edit:
            self.fail_edit = False
            raise DiscordFailure('Temporary edit failure', retry=True)
        self.edits.append(message_id)
        if self.on_edit:
            callback, self.on_edit = self.on_edit, None
            await callback()


class SocialDeliveryBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.repository = SocialRepository(prepare_database(Path(directory.name) / 'review.db', self.addCleanup))
        self.settings = GuildSettingsRepository(self.repository.database_url)
        self.settings.set_module(1, 'twitch_updates', enabled=True)
        self.subscription = self.repository.save_social_subscription_v2(1, 'twitch', 'creator', 10,
            ['live_start', 'live_end'], {}, default_templates('twitch'))
        self.port = PublicationPort()
        self.service = SocialDeliveryService(self.repository, self.settings, self.port)

    @staticmethod
    def event(kind, stream):
        return dict(provider='twitch', account_id='creator', event_type=kind,
            external_event_id=stream, event_key=f'twitch:{kind}:{stream}', payload={'account': 'creator'})

    def change_destination(self, channel_id):
        self.repository.save_social_subscription_v2(1, 'twitch', 'creator', channel_id,
            ['live_start', 'live_end'], {}, default_templates('twitch'), subscription_id=self.subscription['id'])

    async def test_recovery_uses_original_channel_after_configuration_change(self):
        event = self.event('live_start', 'A')
        with patch.object(self.repository, 'update_social_delivery', side_effect=RuntimeError('Commit failed')):
            with self.assertRaises(RuntimeError):
                await self.service.deliver(event)
        self.change_destination(11)
        self.port.unavailable.add(11)
        self.assertTrue(await self.service.deliver(event))
        self.assertEqual(self.port.sends, [(10, False), (10, True)])
        self.assertEqual(len(self.port.messages), 1)
        self.assertEqual(self.repository.social_delivery(self.subscription['id'], event['event_key'])['state'], 'sent')
        self.assertEqual(self.repository.social_live_message(self.subscription['id'], 'twitch', 'creator'),
                         {'discord_channel_id': 10, 'discord_message_id': 1})

    async def test_delayed_end_retries_its_original_publication(self):
        await self.service.deliver(self.event('live_start', 'A'))
        end = self.event('live_end', 'A')
        self.port.fail_edit = True
        self.assertFalse(await self.service.deliver(end))
        await self.service.deliver(self.event('live_start', 'B'))
        # A queue retry is due after the delivery backoff.
        with patch('social.repository.time.time', return_value=4102444800):
            self.assertTrue(await self.service.deliver(end))
        self.assertEqual(self.port.edits, [1])
        self.assertEqual(self.repository.social_live_message(self.subscription['id'], 'twitch', 'creator')['discord_message_id'], 2)

    async def test_sent_end_replay_has_no_external_effect(self):
        await self.service.deliver(self.event('live_start', 'A'))
        end = self.event('live_end', 'A')
        await self.service.deliver(end)
        await self.service.deliver(self.event('live_start', 'B'))
        self.assertTrue(await self.service.deliver(end))
        self.assertEqual(self.port.edits, [1])
        self.assertEqual(len(self.port.messages), 2)
        self.assertEqual(self.repository.social_live_message(self.subscription['id'], 'twitch', 'creator')['discord_message_id'], 2)

    async def test_end_completion_does_not_clear_a_new_live_reference(self):
        await self.service.deliver(self.event('live_start', 'A'))
        self.port.on_edit = lambda: self.service.deliver(self.event('live_start', 'B'))
        self.assertTrue(await self.service.deliver(self.event('live_end', 'A')))
        self.assertEqual(self.port.edits, [1])
        self.assertEqual(self.repository.social_live_message(self.subscription['id'], 'twitch', 'creator')['discord_message_id'], 2)
    async def test_old_sent_start_replay_preserves_newer_live_reference(self):
        start_a = self.event('live_start', 'A')
        await self.service.deliver(start_a)
        await self.service.deliver(self.event('live_start', 'B'))
        self.assertTrue(await self.service.deliver(start_a))
        self.assertEqual(self.repository.social_live_message(self.subscription['id'], 'twitch', 'creator')['discord_message_id'], 2)
        self.assertEqual(len(self.port.messages), 2)

    async def test_old_sent_start_replay_does_not_resurrect_ended_publication(self):
        start = self.event('live_start', 'A')
        await self.service.deliver(start)
        await self.service.deliver(self.event('live_end', 'A'))
        self.assertTrue(await self.service.deliver(start))
        self.assertIsNone(self.repository.social_live_message(self.subscription['id'], 'twitch', 'creator'))

    async def test_first_delayed_end_with_stream_id_edits_matching_start(self):
        await self.service.deliver(self.event('live_start', 'A'))
        await self.service.deliver(self.event('live_start', 'B'))
        self.assertTrue(await self.service.deliver(self.event('live_end', 'A')))
        self.assertEqual(self.port.edits, [1])
        self.assertEqual(self.repository.social_live_message(self.subscription['id'], 'twitch', 'creator')['discord_message_id'], 2)

    async def test_slow_start_completion_preserves_newer_start(self):
        self.port.on_send = lambda: self.service.deliver(self.event('live_start', 'B'))
        self.assertTrue(await self.service.deliver(self.event('live_start', 'A')))
        self.assertEqual(self.repository.social_live_message(self.subscription['id'], 'twitch', 'creator')['discord_message_id'], 2)

    async def test_sent_end_replay_repairs_reference_clear_after_database_failure(self):
        await self.service.deliver(self.event('live_start', 'A'))
        end = self.event('live_end', 'A')
        with patch.object(self.repository, 'clear_social_live_message', side_effect=RuntimeError('Commit failed')):
            with self.assertRaises(RuntimeError):
                await self.service.deliver(end)
        self.assertTrue(await self.service.deliver(end))
        self.assertEqual(self.port.edits, [1])
        self.assertIsNone(self.repository.social_live_message(self.subscription['id'], 'twitch', 'creator'))

    async def test_missing_edit_target_falls_back_to_recoverable_send(self):
        await self.service.deliver(self.event('live_start', 'A'))
        end = self.event('live_end', 'A')
        self.port.missing_edit = True
        original_update = self.repository.update_social_delivery

        def fail_after_send(subscription_id, event_key, message_id, state='sent'):
            if event_key == end['event_key'] and message_id == 2:
                raise RuntimeError('Commit failed')
            return original_update(subscription_id, event_key, message_id, state)

        with patch.object(self.repository, 'update_social_delivery', side_effect=fail_after_send):
            with self.assertRaises(RuntimeError):
                await self.service.deliver(end)
        self.assertTrue(await self.service.deliver(end))
        self.assertEqual(len(self.port.messages), 2)
        self.assertEqual(self.port.sends, [(10, False), (10, False), (10, True)])
        self.assertIsNone(self.repository.social_live_message(self.subscription['id'], 'twitch', 'creator'))
        await self.service.deliver(self.event('live_start', 'A'))
        self.assertIsNone(self.repository.social_live_message(self.subscription['id'], 'twitch', 'creator'))
