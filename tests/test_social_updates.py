import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord

from cryptography.fernet import Fernet

from cogs.social_updates import SocialUpdatesCog
from social_crypto import SocialTokenCipher
from social_models import default_templates
from storage import GuildStorage


class SocialUpdateTests(unittest.TestCase):
    def test_template_replaces_only_supported_variables(self):
        text = SocialUpdatesCog.render_template("{account}: {title} {unknown}", {"account": "Tueka", "title": "Live"})
        self.assertEqual(text, "Tueka: Live {unknown}")

    def test_template_is_bounded(self):
        self.assertLessEqual(len(SocialUpdatesCog.render_template("x" * 3000, {})), 1900)

    def test_oauth_tokens_are_encrypted_at_the_storage_boundary(self):
        cipher = SocialTokenCipher(Fernet.generate_key().decode("ascii"))
        encrypted = cipher.encrypt("secret-token")
        self.assertNotEqual(encrypted, "secret-token")
        self.assertEqual(cipher.decrypt(encrypted), "secret-token")


class SocialDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_current_live_start_and_end_do_not_fall_back_to_old_live(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = GuildStorage(Path(directory) / 'test.db')
            storage.save_social_subscription_v2(1, 'twitch', 'creator', 10, ['live'], {},
                                                default_templates('twitch', ['live']))
            storage.set_module(1, 'twitch_updates', enabled=True)
            channel = MagicMock(spec=discord.TextChannel)
            channel.id = 10
            message = SimpleNamespace(id=20, edit=AsyncMock())
            channel.send = AsyncMock(return_value=message)
            channel.fetch_message = AsyncMock(return_value=message)
            guild = SimpleNamespace(get_channel=lambda _: channel, get_role=lambda _: None)
            cog = SocialUpdatesCog.__new__(SocialUpdatesCog)
            cog.storage = storage
            cog.bot = SimpleNamespace(get_guild=lambda _: guild)
            event = {'provider': 'twitch', 'account_id': 'creator', 'event_type': 'live_start',
                     'event_key': 'twitch:live_start:one', 'payload': {'account': 'creator', 'title': 'live'}}
            self.assertTrue(await cog._deliver(event))
            channel.send.assert_not_awaited()
            current = storage.save_social_subscription_v2(2, 'twitch', 'creator', 10,
                ['live_start', 'live_end'], {}, default_templates('twitch'))
            storage.set_module(2, 'twitch_updates', enabled=True)
            self.assertTrue(await cog._deliver(event))
            channel.send.assert_awaited_once()
            self.assertEqual(storage.social_live_message(current['id'], 'twitch', 'creator')['discord_message_id'], 20)
            self.assertTrue(await cog._deliver({**event, 'event_type': 'live_end', 'event_key': 'twitch:live_end:one'}))
            message.edit.assert_awaited_once()
            channel.send.assert_awaited_once()
            self.assertIsNone(storage.social_live_message(current['id'], 'twitch', 'creator'))
