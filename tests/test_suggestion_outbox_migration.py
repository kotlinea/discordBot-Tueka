import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from migrate import MIGRATIONS, apply


class SuggestionOutboxMigrationTests(unittest.TestCase):
    def test_real_previous_schema_preserves_rows_and_only_queues_uncertain_publications(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = root / 'previous'
            previous.mkdir()
            for path in sorted(MIGRATIONS.glob('*.sql'))[:8]:
                shutil.copyfile(path, previous / path.name)
            database = root / 'test.db'
            apply(database, root / 'snapshots', previous)
            with closing(sqlite3.connect(database)) as c:
                for identifier, status, message in [(1, 'pending', None), (2, 'reviewing', None),
                        (3, 'approved', 100), (4, 'rejected', None), (5, 'delivery_failed', None)]:
                    c.execute('INSERT INTO suggestions(id,guild_id,channel_id,message_id,author_id,answers_json,status,created_at,updated_at) VALUES(?,1,10,?,20,?, ?,100,100)',
                              (identifier, message, '{"idea":"preserved"}', status))
                c.execute('INSERT INTO suggestion_votes VALUES(1,30,1,100,100)')
                c.execute("INSERT INTO suggestion_events VALUES(1,1,1,20,'created','{}',100)")
                c.commit()
                before = {name: c.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall()
                          for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='schema_migrations'").fetchall()}
            result = apply(database, root / 'snapshots')
            self.assertEqual(result['applied'], ['0009_suggestion_outbox.sql', '0010_resource_leases.sql'])
            with closing(sqlite3.connect(database)) as c:
                for name, rows in before.items():
                    self.assertEqual(c.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall(), rows, name)
                queued = c.execute('SELECT suggestion_id,action,payload_json FROM suggestion_outbox ORDER BY id').fetchall()
                self.assertEqual([(row[0], row[1], json.loads(row[2])) for row in queued],
                                 [(1, 'publish', {'recover': True}), (2, 'publish', {'recover': True})])
                self.assertEqual(c.execute('PRAGMA integrity_check').fetchone(), ('ok',))
                self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(apply(database, root / 'snapshots'), {'applied': [], 'snapshot': None})
