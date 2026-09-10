import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from scripts.db_inventory import backup, inventory


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.db'

    def test_backup_includes_committed_wal_and_restores_to_new_database(self):
        with closing(sqlite3.connect(self.source)) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('PRAGMA wal_autocheckpoint=0')
            connection.execute('CREATE TABLE items(id INTEGER PRIMARY KEY, body TEXT)')
            connection.execute("INSERT INTO items VALUES(1,'private content')")
            connection.commit()
            snapshot = self.root / 'backup.db'
            result = backup(self.source, snapshot)
            self.assertEqual(result['tables'][0]['rows'], 1)
            self.assertNotIn('private content', str(result))
            restored = self.root / 'restore.db'
            self.assertEqual(backup(snapshot, restored), result)
            with closing(sqlite3.connect(restored)) as check:
                self.assertEqual(check.execute('SELECT body FROM items').fetchone()[0], 'private content')

    def test_missing_source_does_not_create_database(self):
        with self.assertRaises(sqlite3.OperationalError):
            backup(self.source, self.root / 'backup.db')
        self.assertFalse(self.source.exists())
        self.assertFalse((self.root / 'backup.db').exists())

    def test_existing_destination_is_not_overwritten(self):
        with closing(sqlite3.connect(self.source)) as connection:
            connection.execute('CREATE TABLE items(id INTEGER)')
        target = self.root / 'backup.db'
        target.write_bytes(b'keep me')
        with self.assertRaises(FileExistsError):
            backup(self.source, target)
        self.assertEqual(target.read_bytes(), b'keep me')

    def test_foreign_key_violation_rejects_snapshot_without_changing_source(self):
        with closing(sqlite3.connect(self.source)) as connection:
            connection.executescript('CREATE TABLE parent(id INTEGER PRIMARY KEY); CREATE TABLE child(parent_id INTEGER REFERENCES parent(id)); INSERT INTO child VALUES(99);')
        self.assertEqual(inventory(self.source)['foreign_key_violations'], 1)
        target = self.root / 'backup.db'
        with self.assertRaises(ValueError):
            backup(self.source, target)
        self.assertFalse(target.exists())
        self.assertEqual(inventory(self.source)['foreign_key_violations'], 1)
