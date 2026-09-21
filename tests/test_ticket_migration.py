"""Current Ticket startup contract after the empty PostgreSQL cutover."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
from discord.ext import commands
from cogs.community.live_stats import LiveStatsCog
from cogs.community.tickets import TicketsCog
from database import connect
from db_support import prepare_database


class TicketStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = prepare_database(self.root / 'ticket', self.addCleanup)

    def assert_no_legacy(self):
        with connect(self.db) as c:
            names = {row['table_name'] for row in c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema()")}
        self.assertFalse(names & {'support_tickets', 'ticket_migrations'})

    def test_legacy_button_is_ignored_and_current_button_is_dispatched(self):
        cog = TicketsCog.__new__(TicketsCog)
        cog.show_open = AsyncMock()
        cog.repository = SimpleNamespace(panel_message_contains=lambda *args: True)
        interaction = SimpleNamespace(type=discord.InteractionType.component,
                                      data={'custom_id': 'tueka-ticket:create'}, guild=SimpleNamespace(id=1), channel_id=10, message=SimpleNamespace(id=900), response=SimpleNamespace(send_message=AsyncMock()))
        asyncio.run(cog.on_interaction(interaction))
        cog.show_open.assert_not_awaited()
        interaction.data['custom_id'] = 'tueka-ticket:open:42'
        asyncio.run(cog.on_interaction(interaction))
        cog.show_open.assert_awaited_once_with(interaction, 42)
        cog.show_open.reset_mock()
        cog.repository.panel_message_contains = lambda *args: False
        awaitable = cog.on_interaction(interaction)
        asyncio.run(awaitable)
        cog.show_open.assert_not_awaited()
        interaction.response.send_message.assert_awaited_once()
        self.assertEqual(LiveStatsCog.__cog_app_commands__, [])
        self.assertIn('open', {command.name for command in cog.ticket.commands})

    def test_bot_loads_current_ticket_commands_without_rollout_settings(self):
        async def load():
            async with commands.Bot(command_prefix='!', intents=discord.Intents.none()) as bot:
                bot.settings = SimpleNamespace(database_url=self.db, data_dir=self.root,
                    ticket_encryption_key=None, ticket_s3_endpoint_url=None, ticket_s3_region=None,
                    ticket_s3_bucket=None, ticket_s3_access_key_id=None, ticket_s3_secret_access_key=None,
                    ticket_s3_prefix='tickets')
                await bot.load_extension('cogs.community.live_stats')
                await bot.load_extension('cogs.community.tickets')
                self.assertEqual({command.name for command in bot.tree.get_commands()}, {'ticket', 't'})
                self.assert_no_legacy()
        asyncio.run(load())

    def test_feedback_from_unrecorded_old_message_cannot_reach_current_ticket(self):
        cog = TicketsCog.__new__(TicketsCog)
        cog.repository = SimpleNamespace(notice_message_recorded=lambda *args: False)
        interaction = SimpleNamespace(type=discord.InteractionType.component,
            data={'custom_id': 'tueka-ticket-feedback:1:5'}, message=SimpleNamespace(id=900),
            response=SimpleNamespace(send_message=AsyncMock()))
        asyncio.run(cog.on_interaction(interaction))
        interaction.response.send_message.assert_awaited_once()
