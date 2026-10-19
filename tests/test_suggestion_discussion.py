"""Thread reconciliation uses the source message identity, never blind replay."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,MagicMock
import discord
from discord_io import DiscordFailure
from suggestions.discord_adapter import DiscordSuggestionAdapter

class SuggestionDiscussionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.thread=MagicMock(spec=discord.Thread)
        self.thread.id=900;self.thread.parent_id=10
        self.message=SimpleNamespace(id=900,thread=None,create_thread=AsyncMock(return_value=self.thread))
        self.channel=MagicMock(spec=discord.TextChannel)
        self.channel.id=10
        self.channel.fetch_message=AsyncMock(return_value=self.message)
        self.channel.guild=SimpleNamespace(get_thread=lambda _:None,fetch_channel=AsyncMock())
        self.channel.guild.fetch_channel.side_effect=discord.NotFound(SimpleNamespace(status=404,reason='Not found'),'Missing')
        bot=SimpleNamespace(get_guild=lambda _:SimpleNamespace(get_channel=lambda _:self.channel))
        self.adapter=DiscordSuggestionAdapter(bot)
        self.item={'id':1,'guild_id':1,'channel_id':10,'message_id':900}

    async def test_first_attempt_creates_one_thread_from_source_message(self):
        self.assertEqual(await self.adapter.discussion(self.item,recover=False),900)
        self.message.create_thread.assert_awaited_once()

    async def test_restart_finds_existing_thread_without_creation(self):
        self.channel.guild.fetch_channel.side_effect=None
        self.channel.guild.fetch_channel.return_value=self.thread
        self.assertEqual(await self.adapter.discussion(self.item,recover=True),900)
        self.message.create_thread.assert_not_awaited()

    async def test_unknown_receipt_retains_reconciliation_hold(self):
        with self.assertRaises(DiscordFailure) as error:await self.adapter.discussion(self.item,recover=True)
        self.assertTrue(error.exception.partial)
        self.message.create_thread.assert_not_awaited()

    async def test_forbidden_does_not_create_or_retry(self):
        self.channel.guild.fetch_channel.side_effect=discord.Forbidden(SimpleNamespace(status=403,reason='Forbidden'),'Denied')
        with self.assertRaises(DiscordFailure) as error:await self.adapter.discussion(self.item,recover=False)
        self.assertFalse(error.exception.retry)
        self.message.create_thread.assert_not_awaited()
