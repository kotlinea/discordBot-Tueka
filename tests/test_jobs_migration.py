import shutil
import tempfile
import unittest
from pathlib import Path

from database import transaction
from jobs import Outcome, QueueRepository
from migrate import MIGRATIONS, apply
from test_jobs import QUEUES


class JobMigrationTests(unittest.TestCase):
    def test_previous_schema_payloads_survive_and_expired_processing_is_reclaimed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / 'old'
            old.mkdir()
            for path in sorted(MIGRATIONS.glob('*.sql'))[:7]:
                shutil.copyfile(path, old / path.name)
            database = root / 'test.db'
            apply(database, root / 'backups', old)
            with transaction(database) as c:
                for spec, columns, values in QUEUES:
                    c.execute(f'INSERT INTO {spec.table}({columns}) VALUES({values})')
                c.execute("UPDATE ticket_outbox SET status='processing',lease_owner='crashed',lease_until=1")
                c.execute("UPDATE reaction_role_outbox SET state='done'")
                before = {}
                for spec, _, _ in QUEUES:
                    columns = [row[1] for row in c.execute(f'PRAGMA table_info({spec.table})')]
                    before[spec.table] = (columns, [tuple(row) for row in c.execute(f'SELECT * FROM {spec.table}')])
            self.assertEqual(apply(database, root / 'backups')['applied'], ['0008_job_leases.sql'])
            with transaction(database) as c:
                for table, (columns, rows) in before.items():
                    self.assertEqual([tuple(row) for row in c.execute(f'SELECT {",".join(columns)} FROM {table}')], rows)
                self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
                self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
            queue = QueueRepository(database, QUEUES[0][0])
            claim = queue.claim('restarted')
            self.assertIsNotNone(claim)
            self.assertTrue(queue.finish(claim, Outcome()))
            self.assertEqual(QueueRepository(database, QUEUES[2][0]).purge(), 0)
            self.assertEqual(apply(database, root / 'backups'), {'applied': [], 'snapshot': None})
