import unittest
import asyncio
from types import SimpleNamespace

from discord import app_commands

from cogs.general import GeneralCog, HelpView, _leaf_commands
from cogs.engagement.roll import MAX_ROLL_SIDES
from cogs.engagement.echo import _build_embed
from cogs.engagement.calculate import _safe_calculate


class GeneralCommandTests(unittest.TestCase):
    def test_split_utility_cogs_preserve_basic_help_order(self):
        import discord
        from discord.ext import commands
        from cogs.engagement.echo import EchoCog
        from cogs.engagement.calculate import CalculateCog
        from cogs.engagement.roll import RollCog
        async def check():
            async with commands.Bot(command_prefix='!', intents=discord.Intents.none()) as bot:
                general = GeneralCog.__new__(GeneralCog)
                general.bot = bot
                await bot.add_cog(general)
                for cog in (EchoCog(), CalculateCog(), RollCog()):
                    await bot.add_cog(cog)
                pages = await general._available_commands(SimpleNamespace(), include_all=True)
                self.assertEqual([(category, [command.name for command in commands]) for category, commands in pages],
                    [('基本', ['help', 'ping', 'echo', 'calculate', 'roll', 'userinfo', 'serverinfo'])])
        asyncio.run(check())

    def test_calculator_accepts_basic_expression(self):
        self.assertEqual(_safe_calculate("2 * (3 + 4)"), 14)

    def test_calculator_rejects_expensive_power(self):
        with self.assertRaises(ValueError):
            _safe_calculate("2 ** 13")

    def test_calculator_rejects_unsupported_syntax(self):
        with self.assertRaises(ValueError):
            _safe_calculate("__import__('os')")

    def test_help_view_disables_first_previous_button(self):
        view = HelpView(1, [("基本", [])])
        self.assertTrue(view.previous.disabled)
        self.assertTrue(view.next.disabled)

    def test_help_expands_command_groups_to_leaf_commands(self):
        group = app_commands.Group(name="ticket", description="Ticket commands")

        @group.command(name="open", description="Open a ticket")
        async def open_ticket(interaction):
            pass

        commands = _leaf_commands(group)
        self.assertEqual([command.qualified_name for command in commands], ["ticket open"])

    def test_roll_limit_is_practical(self):
        self.assertEqual(MAX_ROLL_SIDES, 1_000_000)

    def test_embed_builder_supports_embed_fields(self):
        embed = _build_embed("Title", "Description", "#5865F2", None, "Author", None, None, "Footer", None, None, None, '[{"name":"Field","value":"Value","inline":true}]', True)
        self.assertEqual(embed.title, "Title")
        self.assertEqual(len(embed.fields), 1)

    def test_embed_builder_rejects_too_many_fields(self):
        fields = "[" + ",".join('{"name":"n","value":"v"}' for _ in range(26)) + "]"
        with self.assertRaises(ValueError):
            _build_embed(None, None, None, None, None, None, None, None, None, None, None, fields, False)
