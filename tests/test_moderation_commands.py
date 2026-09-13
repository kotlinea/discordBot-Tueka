from guild_settings import GuildSettingsRepository
from db_support import prepare_database
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import discord
from discord.ext import commands
from moderation import ModerationRepository


class ModerationCommandLoadTests(unittest.IsolatedAsyncioTestCase):
    async def test_automod_startup_preserves_data_without_csv_or_runtime_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'moderation.sqlite3'
            storage = ModerationRepository(prepare_database(path))
            GuildSettingsRepository(storage.database_path).set_module(1, 'moderation', enabled=True, settings={'escalation_enabled': True})
            with storage._connection() as connection:
                connection.execute('INSERT INTO guild_users(guild_id,user_id,xp) VALUES(1,2,3)')
            def rows():
                with storage._connection() as connection:
                    names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                    return {name: [tuple(row) for row in connection.execute(f'SELECT * FROM "{name}" ORDER BY rowid')] for name in names}
            before = rows()
            async with commands.Bot(command_prefix='!', intents=discord.Intents.none()) as bot:
                bot.settings = SimpleNamespace(database_path=prepare_database(path))
                await bot.load_extension('cogs.automod')
                await bot.load_extension('cogs.moderation')
                await bot.load_extension('cogs.safety')
                self.assertEqual(rows(), before)
                cog = bot.get_cog('AutoModCog')
                self.assertIn('on_message', {name for name, _ in cog.get_listeners()})

    async def test_mod_group_loads_without_discord_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            bot = commands.Bot(command_prefix="/", intents=discord.Intents.none())
            bot.settings = SimpleNamespace(database_path=prepare_database(Path(directory) / "moderation.sqlite3"))
            async with bot:
                await bot.load_extension("cogs.moderation_commands")
                group = bot.tree.get_command("mod")
                self.assertIsNotNone(group)
                self.assertEqual(
                    {command.name for command in group.commands},
                    {"warn", "timeout", "untimeout", "kick", "ban", "softban", "unban", "purge", "lock", "unlock", "lockdown", "unlockdown"},
                )
