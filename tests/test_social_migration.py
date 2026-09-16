from guild_settings import GuildSettingsRepository
from db_support import prepare_database, set_fixture_version
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from migrate import apply
from social.models import default_templates
from social import SocialRepository


class SocialRemovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'test.db'
        self.backups = self.root / 'backups'

    def seed(self, mixed=True):
        directory = self.root / (self.db.stem + '-previous')
        directory.mkdir()
        for path in Path('migrations').glob('*.sql'):
            if int(path.name[:4]) <= 5:
                shutil.copy(path, directory)
        prepare_database(self.db)
        store = SocialRepository(self.db)
        subscription = store.save_social_subscription_v2(1, 'youtube', 'UC1', 10, ['video'], {},
                                                        default_templates('youtube', ['video']))
        GuildSettingsRepository(store.database_path).set_module(1, 'youtube_updates', enabled=False)
        store.enqueue_social_event_v2('youtube', 'event1', 'UC1', 'video', {'title': 'keep'})
        store.record_social_delivery(subscription['id'], 'youtube:video:event1', 10, 20, 'sent')
        store.set_social_live_message(subscription['id'], 'youtube', 'UC1', 10, 20)
        with store._connection() as connection:
            connection.execute("ALTER TABLE social_subscriptions ADD COLUMN template TEXT NOT NULL DEFAULT ''")
            connection.execute("UPDATE social_targets SET cursor_json=?,revision=9 WHERE id=?",
                               ('{"last_seen":"keep"}', subscription['target_id']))
            if mixed:
                connection.execute("""INSERT INTO social_subscriptions
                    (id,guild_id,provider,account_id,account_name,channel_id,events_json,created_at,updated_at,template)
                    VALUES(99,2,'twitch','old','old',11,'["live"]',1,1,'old text')""")
        set_fixture_version(self.db, 5)
        return subscription

    def retained(self):
        with closing(sqlite3.connect(self.db)) as connection:
            names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='schema_migrations'")]
            values = {'suggestion_outbox': []}  # Must remain empty for this domain fixture.
            for name in names:
                columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{name}")')
                           if not (name == 'social_subscriptions' and row[1] == 'template')]
                fields = ','.join('"' + col + '"' for col in columns)
                values[name] = connection.execute(f'SELECT {fields} FROM "{name}" ORDER BY rowid').fetchall()
            return values

    def test_current_data_and_unconverted_rows_survive_migration_and_restart(self):
        for mixed in (False, True):
            with self.subTest(mixed=mixed):
                self.db = self.root / f'{mixed}.db'
                subscription = self.seed(mixed)
                before = self.retained()
                before['sqlite_sequence'].append(('suggestion_outbox', 0))
                result = apply(self.db, self.backups)
                self.assertEqual(result['applied'], ['0006_remove_legacy_social_template.sql', '0007_current_schema.sql', '0008_job_leases.sql', '0009_suggestion_outbox.sql', '0010_resource_leases.sql'])
                for _ in range(2):
                    store = SocialRepository(self.db)
                    self.assertEqual(self.retained(), before)
                    self.assertFalse(GuildSettingsRepository(store.database_path).module_enabled(1, 'youtube_updates'))
                    self.assertEqual(store.social_target(subscription['target_id'])['cursor'], {'last_seen': 'keep'})
                    self.assertEqual(len(store.matching_social_subscriptions('youtube', 'UC1', 'video')), 1)
                    if mixed:
                        self.assertIsNone(store.social_subscription(99)['target_id'])
                        self.assertEqual(store.social_targets('twitch'), [])
                        self.assertFalse(GuildSettingsRepository(store.database_path).module_enabled(2, 'twitch_updates'))
                        self.assertEqual(store.matching_social_subscriptions('twitch', 'old', 'live'), [])
                with closing(sqlite3.connect(self.db)) as connection:
                    self.assertNotIn('template', {row[1] for row in connection.execute('PRAGMA table_info(social_subscriptions)')})
                    self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
                    self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone(), ('ok',))
                with closing(sqlite3.connect(result['snapshot'])) as snapshot:
                    self.assertIn('template', {row[1] for row in snapshot.execute('PRAGMA table_info(social_subscriptions)')})
                self.assertEqual(apply(self.db, self.backups), {'applied': [], 'snapshot': None})
                self.assertIsNotNone(store.event_jobs.claim('worker'))

    def test_failure_restores_column_rows_and_history(self):
        self.seed()
        with closing(sqlite3.connect(self.db)) as connection:
            before = list(connection.iterdump())
        directory = self.root / 'failure'
        shutil.copytree('migrations', directory)
        (directory / '0011_fail.sql').write_text('INSERT INTO missing_table VALUES(1);')
        with self.assertRaises(sqlite3.OperationalError):
            apply(self.db, self.backups, directory)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(list(connection.iterdump()), before)
