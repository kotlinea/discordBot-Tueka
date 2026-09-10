import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from migrate import apply
from scripts.db_inventory import inventory
from suggestions import SuggestionRepository


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'test.db'
        self.backups = self.root / 'backups'

    def sql(self, text):
        directory = self.root / 'migrations'
        directory.mkdir(exist_ok=True)
        (directory / '0001_test.sql').write_text(text, encoding='utf-8')
        return directory

    def seed(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute('CREATE TABLE preserved(id INTEGER PRIMARY KEY, value TEXT)')
            connection.execute("INSERT INTO preserved VALUES(1,'keep')")
            connection.commit()

    def test_empty_database_and_reapplication(self):
        result = apply(self.db, self.backups)
        self.assertEqual(result['applied'], ['0001_suggestions.sql'])
        self.assertEqual(inventory(Path(result['snapshot']))['tables'], [])
        repository = SuggestionRepository(self.db)
        item = repository.create(1, 2, 3, {'idea': 'keep'})
        before = inventory(self.db)
        self.assertEqual(apply(self.db, self.backups), {'applied': [], 'snapshot': None})
        self.assertEqual(inventory(self.db), before)
        self.assertEqual(repository.get(1, item['id'])['answers'], {'idea': 'keep'})

    def test_existing_v2_data_is_preserved(self):
        repository = SuggestionRepository(self.db)
        item = repository.create(1, 2, 3, {'idea': 'existing'})
        result = apply(self.db, self.backups)
        self.assertTrue(Path(result['snapshot']).exists())
        self.assertEqual(repository.get(1, item['id'])['answers'], {'idea': 'existing'})

    def test_failed_ddl_rolls_back_data_schema_and_history(self):
        self.seed()
        before = inventory(self.db)
        directory = self.sql('DROP TABLE preserved; CREATE TABLE partial(id INTEGER); INSERT INTO missing VALUES(1);')
        with self.assertRaises(sqlite3.OperationalError):
            apply(self.db, self.backups, directory)
        self.assertEqual(inventory(self.db), before)
        snapshot, = self.backups.glob('*.sqlite3')
        self.assertEqual(inventory(snapshot), before)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('SELECT value FROM preserved').fetchone()[0], 'keep')

    def test_commit_in_migration_cannot_escape_rollback(self):
        self.seed()
        directory = self.sql('DROP TABLE preserved; COMMIT;')
        with self.assertRaises(sqlite3.DatabaseError):
            apply(self.db, self.backups, directory)
        self.assertEqual(inventory(self.db)['tables'][0]['name'], 'preserved')

    def test_history_checksum_change_is_rejected(self):
        directory = self.sql('CREATE TABLE example(id INTEGER);')
        apply(self.db, self.backups, directory)
        self.sql('CREATE TABLE example(id TEXT);')
        with self.assertRaisesRegex(ValueError, 'history'):
            apply(self.db, self.backups, directory)
        self.assertEqual(len(list(self.backups.glob('*.sqlite3'))), 1)

    def test_backup_failure_prevents_migration(self):
        self.seed()
        self.backups.write_text('not a directory')
        with self.assertRaises(FileExistsError):
            apply(self.db, self.backups)
        self.assertEqual([table['name'] for table in inventory(self.db)['tables']], ['preserved'])

    def test_second_version_and_foreign_key_failure_rollback(self):
        directory = self.sql('CREATE TABLE parent(id INTEGER PRIMARY KEY); CREATE TABLE child(parent_id INTEGER REFERENCES parent(id));')
        apply(self.db, self.backups, directory)
        (directory / '0002_invalid.sql').write_text('INSERT INTO child VALUES(99);')
        with self.assertRaises(sqlite3.IntegrityError):
            apply(self.db, self.backups, directory)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0], 1)
        (directory / '0002_invalid.sql').write_text('INSERT INTO parent VALUES(99); INSERT INTO child VALUES(99);')
        self.assertEqual(apply(self.db, self.backups, directory)['applied'], ['0002_invalid.sql'])
