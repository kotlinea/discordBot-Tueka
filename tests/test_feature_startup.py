"""Real Discord extension registration remains atomic and runs once per Bot."""
import asyncio
from dataclasses import replace
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from bot import TuekaBot
from config import Settings
from db_support import prepare_database


class FeatureStartupTests(unittest.IsolatedAsyncioTestCase):
    def settings(self, root, extensions):
        database = prepare_database(root / 'test.db', self.addCleanup)
        with patch.dict(os.environ, {'DISCORD_TOKEN': 'test', 'DATABASE_URL': str(database), 'DATA_DIR': str(root)}, clear=True):
            return replace(Settings.from_env(), extensions=extensions)

    async def test_concurrent_setup_registers_once_and_closes_once(self):
        with tempfile.TemporaryDirectory() as scratch:
            settings = self.settings(Path(scratch), ('cogs.general',))
            heartbeat = AsyncMock()
            with patch('bot.ServiceHeartbeat') as heartbeat_type:
                heartbeat_type.return_value.start = AsyncMock(return_value=heartbeat)
                async with TuekaBot(settings) as bot:
                    with patch.object(bot, 'load_extension', wraps=bot.load_extension) as load, \
                         patch.object(bot.tree, 'sync', AsyncMock(return_value=[])) as sync:
                        await asyncio.gather(bot.setup_hook(), bot.setup_hook())
                    self.assertEqual(load.call_count, 1)
                    sync.assert_awaited_once()
                    self.assertIsNotNone(bot.tree.get_command('help'))
                heartbeat.stop.assert_awaited_once()

    async def test_duplicate_commands_fail_before_sync_and_rollback_loaded_extensions(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            names = ('g1_first_extension', 'g1_second_extension')
            source = '''
from discord import app_commands
async def handler(interaction): pass
async def setup(bot):
    bot.tree.add_command(app_commands.Command(name='same', description='same', callback=handler))
'''
            for name in names:
                (root / f'{name}.py').write_text(source)
            sys.path.insert(0, scratch)
            try:
                async with TuekaBot(self.settings(root, names)) as bot:
                    with patch.object(bot.tree, 'sync', AsyncMock()) as sync:
                        with self.assertRaises(Exception) as raised:
                            await bot.setup_hook()
                    self.assertIn('same', str(raised.exception))
                    self.assertFalse(bot.extensions)
                    self.assertIsNone(bot.tree.get_command('same'))
                    self.assertFalse(bot._features_ready)
                    self.assertIsNone(bot.heartbeat)
                    sync.assert_not_awaited()
            finally:
                sys.path.remove(scratch)
                for name in names:
                    sys.modules.pop(name, None)

    async def test_duplicate_extension_targets_start_nothing(self):
        with tempfile.TemporaryDirectory() as scratch:
            settings = self.settings(Path(scratch), ('cogs.general', 'cogs.general'))
            async with TuekaBot(settings) as bot:
                with patch.object(bot, 'load_extension', AsyncMock()) as load, \
                     self.assertRaisesRegex(ValueError, 'Duplicate runtime'):
                    await bot.setup_hook()
                load.assert_not_awaited()
