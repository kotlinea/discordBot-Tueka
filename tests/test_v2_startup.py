"""Offline entry-point restart check; real Discord/provider I/O belongs to Stage."""
import importlib.util
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock, patch

from bot import TuekaBot
from config import Settings
from migrate import apply
from social_worker import SocialWorker
from database import SchemaNotReady, readonly
from db_support import set_fixture_version


class V2StartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_pending_schema_stops_all_entry_points_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / 'test.db'
            apply(db, root / 'backups')
            set_fixture_version(db, 6)
            with closing(readonly(db)) as connection:
                before = list(connection.iterdump())
            env = {'DISCORD_TOKEN': 'test-token', 'DISCORD_CLIENT_ID': '1',
                   'DISCORD_CLIENT_SECRET': 'test-secret', 'SESSION_SECRET': 'test-session',
                   'DISCORD_REDIRECT_URI': 'http://testserver/oauth/callback',
                   'DATA_DIR': str(root), 'DATABASE_PATH': str(db)}
            with patch.dict(os.environ, env, clear=True):
                settings = Settings.from_env()
                for entry in (TuekaBot, SocialWorker):
                    with self.assertRaisesRegex(SchemaNotReady, 'migrate.py'):
                        entry(settings)
                spec = importlib.util.spec_from_file_location('dashboard_pending', 'dashboard/app.py')
                module = importlib.util.module_from_spec(spec)
                with self.assertRaises(SchemaNotReady):
                    spec.loader.exec_module(module)
            with closing(readonly(db)) as connection:
                self.assertEqual(list(connection.iterdump()), before)

    async def test_all_bot_extensions_dashboard_and_worker_restart_without_v1(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / 'test.db'
            env = {'DISCORD_TOKEN': 'test-token', 'DISCORD_CLIENT_ID': '1',
                   'DISCORD_CLIENT_SECRET': 'test-secret', 'SESSION_SECRET': 'test-session',
                   'DISCORD_REDIRECT_URI': 'http://testserver/oauth/callback',
                   'DATA_DIR': str(root), 'DATABASE_PATH': str(db)}
            apply(db, root / 'backups')
            (root / '1.json').write_text('{"users":{"99":{"xp":999}}}')
            previous_schema = None
            with patch.dict(os.environ, env, clear=True):
                settings = Settings.from_env()
                for iteration in range(2):
                    async with TuekaBot(settings) as bot:
                        with patch.object(bot.tree, 'sync', AsyncMock(return_value=[])):
                            await bot.setup_hook()
                        self.assertEqual(set(bot.extensions), set(settings.extensions))
                        self.assertIsNotNone(bot.tree.get_command('mod'))
                        self.assertIsNotNone(bot.tree.get_command('ticket'))
                    spec = importlib.util.spec_from_file_location(f'dashboard_restart_{iteration}', 'dashboard/app.py')
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    async with module.dashboard_lifespan(module.app):
                        self.assertEqual(module.storage.get_user(1, 99), {'xp': 0})
                    worker = SocialWorker(settings)
                    self.assertEqual(worker.storage.get_user(1, 99), {'xp': 0})
                    with closing(sqlite3.connect(db)) as connection:
                        schema = connection.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
                        names = {name for name, _ in schema}
                        self.assertFalse(names & {'guild_settings', 'support_tickets', 'ticket_migrations',
                            'reaction_role_panels', 'automod_rules', 'automod_events',
                            'automod_migrations', 'moderation_migrations'})
                        for table, columns in {'social_subscriptions': {'template'}, 'guild_users': {'warn'},
                            'moderation_rules': {'legacy_rule_id'},
                            'moderation_cases': {'rule_id', 'automod_event_id'},
                            'moderation_points': {'rule_id', 'automod_event_id'}}.items():
                            self.assertFalse(columns & {row[1] for row in connection.execute(f'PRAGMA table_info({table})')})
                        self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
                        if previous_schema is not None:
                            self.assertEqual(schema, previous_schema)
                        previous_schema = schema
            self.assertEqual(apply(db, root / 'backups'), {'applied': [], 'snapshot': None})
