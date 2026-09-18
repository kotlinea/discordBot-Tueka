"""PostgreSQL inventory and logical-backup CLI safeguards."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from database import transaction
from database.operations import backup, inventory, restore
from db_support import prepare_database


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.url = prepare_database(self.root / 'source', self.addCleanup)

    def test_inventory_reports_schema_and_counts_without_row_contents(self):
        with transaction(self.url) as c:
            c.execute("INSERT INTO app_metadata VALUES('private-key','private-content')")
        result = inventory(self.url)
        self.assertEqual(next(t for t in result['tables'] if t['name'] == 'app_metadata')['rows'], 1)
        self.assertNotIn('private-content', str(result))
        self.assertNotIn('private-key', str(result))
        self.assertEqual(result['backend'], 'postgresql')

    def test_existing_destination_is_not_overwritten(self):
        target = self.root / 'backup.dump'
        target.write_bytes(b'keep')
        with patch('database.operations.subprocess.run') as run:
            with self.assertRaises(FileExistsError):
                backup(self.url, target)
            run.assert_not_called()
        self.assertEqual(target.read_bytes(), b'keep')

    def test_failed_dump_removes_only_its_partial_artifact(self):
        target = self.root / 'backup.dump'
        with patch('database.operations.subprocess.run', return_value=SimpleNamespace(returncode=1, stderr=b'secret')):
            with self.assertRaises(RuntimeError) as error:
                backup(self.url, target)
        self.assertNotIn('secret', str(error.exception))
        self.assertFalse(target.exists())

    def test_dump_uses_environment_credentials_and_custom_format(self):
        def dump(command, **options):
            self.assertEqual(command, ['pg_dump', '--format=custom', '--no-owner', '--no-privileges'])
            self.assertNotIn(self.url, str(command))
            self.assertIn('PGDATABASE', options['env'])
            options['stdout'].write(b'PGDMP')
            return SimpleNamespace(returncode=0)
        target = self.root / 'backup.dump'
        with patch('database.operations.subprocess.run', side_effect=dump):
            self.assertEqual(backup(self.url, target)['bytes'], 5)

    def test_restore_refuses_populated_database_before_starting_client(self):
        with patch('database.operations.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'empty database'):
                restore(self.root / 'missing.dump', self.url)
            run.assert_not_called()
