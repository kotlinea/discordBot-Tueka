from community import CommunityRepository
"""Offline entry-point restart check; real Discord/provider I/O belongs to Stage."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from bot import TuekaBot
from config import Settings
from migrate import apply
from social.worker import SocialWorker
from database import SchemaNotReady, connect
from db_support import prepare_database, snapshot


class V2StartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_pending_schema_stops_all_entry_points_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = prepare_database(root / 'test.db', self.addCleanup)
            with connect(db) as connection:
                connection.execute('DELETE FROM schema_migrations')
            before = snapshot(db)
            env = {'DISCORD_TOKEN': 'test-token', 'DISCORD_CLIENT_ID': '1',
                   'DISCORD_CLIENT_SECRET': 'test-secret', 'SESSION_SECRET': 'test-session',
                   'DISCORD_REDIRECT_URI': 'http://testserver/oauth/callback',
                   'DATA_DIR': str(root), 'DATABASE_URL': str(db)}
            with patch.dict(os.environ, env, clear=True):
                settings = Settings.from_env()
                for entry in (TuekaBot, SocialWorker):
                    with self.assertRaisesRegex(SchemaNotReady, 'migrate.py'):
                        entry(settings)
                spec = importlib.util.spec_from_file_location('dashboard_pending', 'dashboard/app.py')
                module = importlib.util.module_from_spec(spec)
                with self.assertRaises(SchemaNotReady):
                    spec.loader.exec_module(module)
            self.assertEqual(snapshot(db), before)

    async def test_all_bot_extensions_dashboard_and_worker_restart_without_v1(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = prepare_database(root / 'test.db', self.addCleanup)
            env = {'DISCORD_TOKEN': 'test-token', 'DISCORD_CLIENT_ID': '1',
                   'DISCORD_CLIENT_SECRET': 'test-secret', 'SESSION_SECRET': 'test-session',
                   'DISCORD_REDIRECT_URI': 'http://testserver/oauth/callback',
                   'DATA_DIR': str(root), 'DATABASE_URL': str(db)}
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
                        self.assertEqual(CommunityRepository(module.social_repository.database_url).get_user(1, 99), {'xp': 0})
                    worker = SocialWorker(settings)
                    self.assertEqual(CommunityRepository(worker.repository.database_url).get_user(1, 99), {'xp': 0})
                    with connect(db) as connection:
                        schema = connection.execute("SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_schema=current_schema() ORDER BY table_name,ordinal_position").fetchall()
                        names = {row["table_name"] for row in schema}
                        self.assertFalse(names & {'guild_settings', 'support_tickets', 'ticket_migrations',
                            'reaction_role_panels', 'automod_rules', 'automod_events',
                            'automod_migrations', 'moderation_migrations'})
                        for table, columns in {'social_subscriptions': {'template'}, 'guild_users': {'warn'},
                            'moderation_rules': {'legacy_rule_id'},
                            'moderation_cases': {'rule_id', 'automod_event_id'},
                            'moderation_points': {'rule_id', 'automod_event_id'}}.items():
                            self.assertFalse(columns & {row["column_name"] for row in schema if row["table_name"] == table})
                        if previous_schema is not None:
                            self.assertEqual(schema, previous_schema)
                        previous_schema = schema
            self.assertEqual(apply(db), {'applied': []})
