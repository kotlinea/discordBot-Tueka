import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
from cogs.community.insights import InsightsCog


class InsightsDiscordTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = object.__new__(InsightsCog)
        self.guild = SimpleNamespace(id=1, unavailable=False, afk_channel=None)
        self.cog.bot = SimpleNamespace(is_ready=lambda: True)
        self.cog._ready = True
        self.cog._claimed = {1}
        self.cog.service = MagicMock()

    def channel(self, kind=discord.TextChannel, channel_id=20):
        result = MagicMock(spec=kind)
        result.id = channel_id
        result.guild = self.guild
        result.is_nsfw.return_value = False
        return result

    async def test_message_metadata_only_and_no_bot_webhook_or_disconnect_collection(self):
        message = SimpleNamespace(guild=self.guild, author=SimpleNamespace(bot=False), webhook_id=None,
                                  channel=self.channel(), id=100, created_at=datetime(2026, 10, 18, tzinfo=timezone.utc))
        await self.cog.on_message(message)
        self.cog.service.message.assert_called_once_with(1, 100, 20, int(message.created_at.timestamp()), bot=False)
        message.webhook_id = 99
        await self.cog.on_message(message)
        message.webhook_id = None
        message.author.bot = True
        await self.cog.on_message(message)
        message.author.bot = False
        self.cog._ready = False
        await self.cog.on_message(message)
        self.assertEqual(self.cog.service.message.call_count, 1)

    def test_nsfw_private_threads_and_afk_are_excluded(self):
        text = self.channel()
        self.assertEqual(self.cog._channel(text), 20)
        text.is_nsfw.return_value = True
        self.assertIsNone(self.cog._channel(text))
        thread = MagicMock(spec=discord.Thread)
        thread.is_private.return_value = True
        thread.parent = self.channel()
        self.assertIsNone(self.cog._channel(thread))
        thread.is_private.return_value = False
        self.assertEqual(self.cog._channel(thread), 20)
        voice = self.channel(discord.VoiceChannel)
        self.guild.afk_channel = voice
        self.assertIsNone(self.cog._channel(voice))
        self.guild.afk_channel = None
        self.assertEqual(self.cog._channel(self.channel(discord.StageChannel)), 20)

    async def test_voice_and_membership_use_metadata_and_join_time(self):
        member = SimpleNamespace(guild=self.guild, id=30, bot=False,
                                 joined_at=datetime(2026, 10, 18, tzinfo=timezone.utc))
        await self.cog.on_voice_state_update(member, SimpleNamespace(channel=self.channel(discord.VoiceChannel)), SimpleNamespace(channel=None))
        self.cog.service.voice.assert_called_once_with(1, 30, 20, None, bot=False)
        await self.cog.on_member_join(member)
        self.cog.service.membership.assert_called_once_with(1, 30, int(member.joined_at.timestamp() * 1000000), joining=True, bot=False)
        member.bot = True
        await self.cog.on_member_remove(member)
        self.assertEqual(self.cog.service.membership.call_count, 1)

    async def test_disconnect_releases_only_this_observer_and_stops_collection(self):
        await self.cog.on_disconnect()
        self.assertFalse(self.cog._ready)
        self.cog.service.release.assert_called_once_with(1)
        self.assertEqual(self.cog._claimed, set())

    async def test_resumed_session_reestablishes_observation_without_waiting_for_ready_event(self):
        await self.cog.on_disconnect()
        self.cog.collect = AsyncMock()
        await self.cog.on_resumed()
        self.assertTrue(self.cog._ready)
        self.cog.collect.assert_awaited_once()
