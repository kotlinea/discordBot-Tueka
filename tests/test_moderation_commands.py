from guild_settings import GuildSettingsRepository
from db_support import prepare_database
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
from discord.ext import commands
from moderation import ModerationRepository


class ModerationCommandLoadTests(unittest.IsolatedAsyncioTestCase):
    async def test_message_match_converts_to_value_context_before_execution(self):
        from cogs.automod import AutoModCog
        from moderation.contracts import ActionContext
        cog = AutoModCog.__new__(AutoModCog)
        cog._locks = {}
        cog.guild_settings = SimpleNamespace(get_module=lambda *args: {'enabled': True, 'settings': {}})
        rule = {'family': 'automod', 'mode': 'enforce', 'id': 1}
        match = SimpleNamespace(rule=rule, reason='matched', details={})
        cog.engine = SimpleNamespace(globally_exempt=lambda *args: False, evaluate=AsyncMock(return_value=[match]))
        cog._context = lambda *args, **kwargs: SimpleNamespace(event_type='message_create', actor_kind='human')
        cog._rules = lambda *args: [rule]
        cog.moderation_repository = SimpleNamespace(create_moderation_event=MagicMock(return_value=1), finish_moderation_event=MagicMock())
        cog.service = SimpleNamespace(execute_actions=AsyncMock(return_value=[{'type': 'delete', 'status': 'success'}]), log_event=AsyncMock())
        guild = SimpleNamespace(id=1, name='Guild')
        author = MagicMock(spec=discord.Member)
        author.id, author.guild, author.name = 2, guild, 'Member'
        author.guild_permissions = discord.Permissions.none()
        channel = SimpleNamespace(id=3, name='Channel')
        message = SimpleNamespace(id=4, guild=guild, author=author, channel=channel, content='matched', attachments=[])
        await cog._process(message)
        value = cog.service.execute_actions.await_args.args[0]
        self.assertIsInstance(value, ActionContext)
        self.assertEqual((value.guild.id, value.member.id, value.message.id), (1, 2, 4))
        cog.moderation_repository.finish_moderation_event.assert_called_once()

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
