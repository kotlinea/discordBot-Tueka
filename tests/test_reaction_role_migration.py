from db_support import prepare_database, set_fixture_version
import shutil
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from cogs.safety import SafetyCog
from migrate import apply
from reaction_roles import ReactionRoleRepository, ReactionRoleService
from storage import GuildStorage
from test_reaction_roles import message


class ReactionRoleRemovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'test.db'
        self.backups = self.root / 'backups'

    def rows(self):
        with closing(sqlite3.connect(self.db)) as connection:
            names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('schema_migrations','reaction_role_panels')")]
            return {name: connection.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall() for name in names}

    def assert_removed(self):
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='reaction_role_panels'").fetchone())
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_empty_database_and_restart(self):
        apply(self.db, self.backups)
        for _ in range(2):
            GuildStorage(self.db)
            repository = ReactionRoleRepository(self.db)
            self.assertFalse(repository.settings(1)['enabled'])
            self.assertEqual(repository.messages(1), [])
            self.assert_removed()
        self.assertEqual(apply(self.db, self.backups), {'applied': [], 'snapshot': None})
        self.assertNotIn('publish_reaction_roles', {command.name for command in SafetyCog.__cog_app_commands__})
        self.assertFalse(hasattr(SafetyCog, 'on_interaction'))

    def test_mixed_and_v2_only_upgrade_preserve_all_current_rows(self):
        for mixed in (False, True):
            with self.subTest(mixed=mixed):
                self.db = self.root / f'{mixed}.db'
                previous = self.root / f'previous-{mixed}'
                previous.mkdir()
                for name in ('0001_suggestions.sql', '0002_remove_legacy_tickets.sql'):
                    shutil.copyfile(Path('migrations') / name, previous / name)
                prepare_database(self.db)
                storage = GuildStorage(self.db)
                repository = ReactionRoleRepository(self.db)
                service = ReactionRoleService(repository)
                config = service.create(1, message(behavior='temp'))
                repository.settings(1)
                mapping = config['mappings'][0]
                repository.activate_assignment(1, config['id'], mapping['id'], 9, 20, int(time.time()) - 1)
                recoverable = service.create(1, message(channel_id=11))
                repository.set_discord_message(recoverable['id'], 100)
                repository.delete_message(1, recoverable['id'], recoverable=True)
                storage.set_module(2, 'reaction_roles', enabled=True, settings={'reaction_role_ids': [900]})
                self.assertFalse(repository.settings(2)['enabled'])
                if mixed:
                    with closing(sqlite3.connect(self.db)) as connection:
                        connection.executescript("CREATE TABLE reaction_role_panels(message_id INTEGER PRIMARY KEY,guild_id INTEGER,role_ids_json TEXT); INSERT INTO reaction_role_panels VALUES(200,2,'[900]');")
                set_fixture_version(self.db, 2)
                before = self.rows()
                result = apply(self.db, self.backups)
                self.assertEqual(result['applied'], ['0003_remove_legacy_reaction_roles.sql', '0004_remove_legacy_moderation.sql', '0005_remove_shared_settings_fallback.sql', '0006_remove_legacy_social_template.sql', '0007_current_schema.sql'])
                if mixed:
                    with closing(sqlite3.connect(result['snapshot'])) as snapshot:
                        self.assertEqual(snapshot.execute('SELECT role_ids_json FROM reaction_role_panels').fetchone()[0], '[900]')
                GuildStorage(self.db)
                repository = ReactionRoleRepository(self.db)
                self.assertEqual(self.rows(), before)
                self.assert_removed()
                self.assertEqual(repository.assignments(9, config_id=config['id'])[0]['role_id'], 20)
                self.assertEqual(repository.due_schedules('restart')[0]['kind'], 'temp_role')
                self.assertTrue(repository.claim_outbox('restart'))
                self.assertIsNotNone(repository.recovery(1, 100))
                self.assertEqual(apply(self.db, self.backups), {'applied': [], 'snapshot': None})

    def test_failed_following_migration_rolls_back_legacy_drop(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.executescript("CREATE TABLE reaction_role_panels(message_id INTEGER PRIMARY KEY,guild_id INTEGER,role_ids_json TEXT); INSERT INTO reaction_role_panels VALUES(1,2,'[3]');")
        directory = self.root / 'failure'
        directory.mkdir()
        for source in Path('migrations').glob('*.sql'):
            shutil.copyfile(source, directory / source.name)
        (directory / '0008_fail.sql').write_text('INSERT INTO missing_table VALUES(1);')
        with self.assertRaises(sqlite3.OperationalError):
            apply(self.db, self.backups, directory)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('SELECT * FROM reaction_role_panels').fetchall(), [(1, 2, '[3]')])
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='schema_migrations'").fetchone())
