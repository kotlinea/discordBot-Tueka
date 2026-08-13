import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import discord
from discord.ext import commands


class ModerationCommandLoadTests(unittest.IsolatedAsyncioTestCase):
    async def test_mod_group_loads_without_discord_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            bot = commands.Bot(command_prefix="/", intents=discord.Intents.none())
            bot.settings = SimpleNamespace(database_path=Path(directory) / "moderation.sqlite3")
            async with bot:
                await bot.load_extension("cogs.moderation_commands")
                group = bot.tree.get_command("mod")
                self.assertIsNotNone(group)
                self.assertEqual(
                    {command.name for command in group.commands},
                    {"warn", "timeout", "untimeout", "kick", "ban", "softban", "unban", "purge", "lock", "unlock", "lockdown", "unlockdown"},
                )
