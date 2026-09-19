"""Native PostgreSQL connection policy and transaction lifecycle."""
import unittest
from pathlib import Path

import psycopg

from database import connect, database_url, transaction
from database.testing import temporary_database


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.context = temporary_database()
        self.url = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)

    def test_file_and_malformed_urls_are_rejected_without_secret_disclosure(self):
        for value in (Path('missing/test.db'), 'sqlite:///test.db', 'postgresql://user:secret@host', 'postgresql://user:secret@host:invalid/db'):
            with self.subTest(kind=type(value).__name__):
                with self.assertRaises(ValueError) as caught:
                    database_url(value)
                self.assertNotIn('secret', str(caught.exception))

    def test_connection_pool_uses_bounded_timeouts_and_utc(self):
        with transaction(self.url) as c:
            for setting, value in [('statement_timeout', '30s'), ('lock_timeout', '10s'), ('idle_in_transaction_session_timeout', '30s'), ('TimeZone', 'UTC')]:
                self.assertEqual(c.execute('SELECT current_setting(%s) AS value', (setting,)).fetchone()['value'], value)
            self.assertFalse(c.info.transaction_status == psycopg.pq.TransactionStatus.IDLE)

    def test_read_only_connection_rejects_writes(self):
        with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):
            with connect(self.url, read_only=True) as c:
                c.execute("INSERT INTO app_metadata VALUES('write','forbidden')")

    def test_exception_and_keyboard_interrupt_roll_back_and_pool_is_reusable(self):
        with transaction(self.url) as c:
            c.execute("INSERT INTO app_metadata VALUES('committed','keep')")
        for error in (ValueError, KeyboardInterrupt):
            with self.assertRaises(error):
                with transaction(self.url) as c:
                    c.execute("INSERT INTO app_metadata VALUES('partial','discard')")
                    raise error()
            with transaction(self.url) as c:
                self.assertEqual(c.execute('SELECT * FROM app_metadata').fetchall(), [{'key': 'committed', 'value': 'keep'}])
        with self.assertRaises(psycopg.IntegrityError):
            with transaction(self.url) as c:
                c.execute("INSERT INTO app_metadata VALUES('partial','discard')")
                c.execute("INSERT INTO app_metadata VALUES('committed','duplicate')")
        with transaction(self.url) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) AS count FROM app_metadata').fetchone()['count'], 1)

    def test_lock_timeout_rolls_back_partial_work(self):
        from concurrent.futures import ThreadPoolExecutor
        with transaction(self.url) as c:
            c.execute("INSERT INTO app_metadata VALUES('locked','original')")
        def competing():
            with transaction(self.url) as c:
                c.execute("SET LOCAL lock_timeout='50ms'")
                c.execute("INSERT INTO app_metadata VALUES('partial','discard')")
                c.execute("UPDATE app_metadata SET value='changed' WHERE key='locked'")
        with connect(self.url) as owner:
            owner.execute("SELECT * FROM app_metadata WHERE key='locked' FOR UPDATE")
            with ThreadPoolExecutor(max_workers=1) as executor:
                with self.assertRaises(psycopg.errors.LockNotAvailable):
                    executor.submit(competing).result(timeout=10)
        with transaction(self.url) as c:
            self.assertEqual(c.execute('SELECT * FROM app_metadata').fetchall(), [{'key': 'locked', 'value': 'original'}])

    def test_connection_loss_discards_uncommitted_work_and_pool_recovers(self):
        with self.assertRaises(psycopg.OperationalError):
            with transaction(self.url) as c:
                c.execute("INSERT INTO app_metadata VALUES('uncommitted','discard')")
                with connect(self.url, autocommit=True) as control:
                    control.execute('SELECT pg_terminate_backend(%s)', (c.info.backend_pid,))
                c.execute('SELECT 1')
        with transaction(self.url) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) AS count FROM app_metadata').fetchone()['count'], 0)
            c.execute("INSERT INTO app_metadata VALUES('recovered','keep')")

    def test_deadlock_rolls_back_one_whole_transaction_without_automatic_replay(self):
        from observability.metrics import registry
        from observability.repository import snapshot
        import time
        def deadlocks():
            return sum(item['value'] for item in registry.snapshot() if item['name'] == 'db_errors_total' and item['labels'].get('category') == 'deadlock')
        before = deadlocks()
        database_before = snapshot(self.url)['database']['deadlocks_total']
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        with transaction(self.url) as c:
            c.execute("INSERT INTO app_metadata VALUES('one','0'),('two','0')")
        barrier = Barrier(2)
        def update(keys):
            try:
                with transaction(self.url) as c:
                    c.execute('UPDATE app_metadata SET value=%s WHERE key=%s', (keys[0], keys[0]))
                    barrier.wait(timeout=5)
                    c.execute('UPDATE app_metadata SET value=%s WHERE key=%s', (keys[0], keys[1]))
                return 'committed'
            except psycopg.errors.DeadlockDetected:
                return 'rolled_back'
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(update, [('one', 'two'), ('two', 'one')]))
        self.assertEqual(sorted(results), ['committed', 'rolled_back'])
        with transaction(self.url) as c:
            values = {row['value'] for row in c.execute('SELECT value FROM app_metadata')}
        self.assertEqual(len(values), 1)
        self.assertNotIn('0', values)
        self.assertEqual(deadlocks(), before + 1)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            database_after = snapshot(self.url)['database']['deadlocks_total']
            if database_after > database_before:
                break
            time.sleep(.1)
        self.assertGreater(database_after, database_before)
