from community import CommunityRepository
from db_support import prepare_database, set_fixture_version
import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from migrate import apply
from guild_settings import GuildSettingsRepository


class SharedSettingsRemovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'test.db'
        self.backups = self.root / 'backups'

    def seed(self):
        directory = self.root / 'previous'
        directory.mkdir()
        for path in Path('migrations').glob('*.sql'):
            if int(path.name[:4]) <= 4:
                shutil.copy(path, directory)
        prepare_database(self.db)
        store = GuildSettingsRepository(self.db)
        CommunityRepository(store.database_path).add_xp(1, 99, 42)
        with closing(sqlite3.connect(self.db)) as connection:
            connection.executescript("""
                CREATE TABLE guild_settings(guild_id INTEGER PRIMARY KEY,
                    management_channel_id INTEGER,welcome_channel_id INTEGER,default_role_id INTEGER);
                INSERT INTO guild_settings VALUES(1,10,11,12),(2,20,21,22),(3,30,31,32);
                INSERT INTO app_metadata VALUES('json_migration_v1','complete'),('keep','value');
            """)
            for guild, module, settings in [
                (1, 'leveling', {'voice_enabled': True}),
                (2, 'leveling', {'text_notification_channel_id': None}),
                (3, 'leveling', {'text_notification_channel_id': 333}),
                (1, 'audit_log', {'management_channel_id': 44}),
                (2, 'audit_log', {'management_channel_id': 55, 'log_voice': False}),
                (1, 'welcome', {'welcome_channel_id': 66, 'welcome_enabled': True}),
            ]:
                connection.execute('INSERT INTO guild_modules VALUES(?,?,?,?,?)',
                                   (guild, module, 1, json.dumps(settings), 7))
            connection.commit()
        set_fixture_version(self.db, 4)

    def test_preserves_effective_settings_revision_and_unrelated_data(self):
        self.seed()
        result = apply(self.db, self.backups)
        self.assertEqual(result['applied'], ['0005_remove_shared_settings_fallback.sql', '0006_remove_legacy_social_template.sql', '0007_current_schema.sql'])
        for _ in range(2):
            store = GuildSettingsRepository(self.db)
            for guild, channel in [(1, 10), (2, None), (3, 333)]:
                value = store.get_module(guild, 'leveling')
                self.assertEqual(value['settings']['text_notification_channel_id'], channel)
                self.assertTrue(value['enabled'])
                self.assertEqual(value['revision'], 7)
            self.assertTrue(store.get_module(1, 'audit_log')['settings']['log_message'])
            self.assertFalse(store.get_module(2, 'audit_log')['settings']['log_message'])
            candidate = store.get_module(3, 'audit_log')
            self.assertFalse(candidate['settings']['log_message'])
            self.assertFalse(candidate['enabled'])
            self.assertEqual(candidate['revision'], 0)
            self.assertEqual(store.get_module(1, 'welcome')['settings']['welcome_channel_id'], 66)
            self.assertEqual(store.get_module(2, 'welcome')['settings']['welcome_channel_id'], 21)
            self.assertEqual(store.get_module(1, 'autorole')['settings']['default_role_id'], 12)
            self.assertEqual(CommunityRepository(store.database_path).get_user(1, 99), {'xp': 42})
            with closing(sqlite3.connect(self.db)) as connection:
                self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='guild_settings'").fetchone())
                self.assertEqual(connection.execute('SELECT * FROM app_metadata').fetchall(), [('keep', 'value')])
                self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
                self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone(), ('ok',))
        self.assertEqual(apply(self.db, self.backups), {'applied': [], 'snapshot': None})
        with closing(sqlite3.connect(result['snapshot'])) as snapshot:
            self.assertEqual(snapshot.execute('SELECT COUNT(*) FROM guild_settings').fetchone()[0], 3)
        saved = store.set_module(3, 'audit_log', enabled=False, expected_revision=0)
        self.assertEqual(saved['revision'], 1)

    def test_failure_restores_settings_marker_and_history(self):
        self.seed()
        with closing(sqlite3.connect(self.db)) as connection:
            before = list(connection.iterdump())
        directory = self.root / 'failure'
        shutil.copytree('migrations', directory)
        (directory / '0008_fail.sql').write_text('INSERT INTO missing_table VALUES(1);')
        with self.assertRaises(sqlite3.OperationalError):
            apply(self.db, self.backups, directory)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(list(connection.iterdump()), before)

    def test_empty_database_does_not_import_json_on_restart(self):
        (self.root / '1.json').write_text('{"users":{"99":{"xp":999}}}')
        apply(self.db, self.backups)
        with closing(sqlite3.connect(self.db)) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO guild_modules(guild_id,module_id,enabled) VALUES(1,'welcome',2)")
        for _ in range(2):
            store = GuildSettingsRepository(self.db)
            self.assertEqual(CommunityRepository(store.database_path).get_user(1, 99), {'xp': 0})
            self.assertIsNone(store.get_module(1, 'leveling')['settings']['text_notification_channel_id'])
            self.assertFalse(hasattr(store, 'migrate_json'))
            self.assertFalse(hasattr(store, 'migrated'))
