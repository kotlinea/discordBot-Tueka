"""Queue state survives explicit reapplication and repository restart."""
import tempfile
import unittest
from pathlib import Path
from database import transaction
from db_support import prepare_database, snapshot
from jobs import Outcome, QueueRepository
from migrate import apply
from test_jobs import QUEUES


class JobMigrationTests(unittest.TestCase):
    def test_current_payloads_survive_and_expired_processing_is_reclaimed(self):
        with tempfile.TemporaryDirectory() as directory:
            database = prepare_database(Path(directory) / 'queues', self.addCleanup)
            with transaction(database) as c:
                for spec, columns, values in QUEUES:
                    c.execute(f'INSERT INTO {spec.table}({columns}) VALUES({values})')
                c.execute("UPDATE ticket_outbox SET status='processing',lease_owner='crashed',lease_until=1")
                c.execute("UPDATE reaction_role_outbox SET state='done'")
            before = snapshot(database)
            self.assertEqual(apply(database), {'applied': []})
            self.assertEqual(snapshot(database), before)
            queue = QueueRepository(database, QUEUES[0][0])
            claim = queue.claim('restarted')
            self.assertIsNotNone(claim)
            self.assertTrue(queue.finish(claim, Outcome()))
            self.assertIsNone(QueueRepository(database, QUEUES[2][0]).claim('completed'))
