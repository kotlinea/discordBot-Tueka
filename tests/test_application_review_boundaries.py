"""Application cooldown evidence must survive private answer expiry."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import shutil
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from applications.repository import ApplicationRepository
from database import transaction
from database.migrations import MIGRATIONS, apply
from database.testing import temporary_database
from db_support import prepare_database
from guild_settings import GuildSettingsRepository
from test_applications import definition


class ApplicationReviewBoundariesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.url = prepare_database(Path(temp.name) / 'application-boundaries', self.addCleanup)
        self.repo = ApplicationRepository(self.url)
        GuildSettingsRepository(self.url).set_module(1, 'applications', enabled=True)
        self.form = self.repo.save_form(1, 900, definition(retention_days=1, cooldown_seconds=2592000))
        self.start = 2_000_000_000

    def submit(self, interaction=100, author=10, form=None, guild=1):
        form = form or self.form
        return self.repo.submit(guild, form['id'], author, interaction, {'why': 'Synthetic answer'},
            revision=form['revision'], roles=[], created_at=1, joined_at=1)

    def test_cooldown_survives_private_answer_and_audit_cleanup(self):
        with patch('applications.repository.time.time', return_value=self.start):
            self.submit()
        with patch('applications.repository.time.time', return_value=self.start + 86401):
            with self.assertRaisesRegex(RuntimeError, 'application_cooldown'):
                self.submit(101)
            self.assertEqual(self.repo.purge_expired(), 1)
            with transaction(self.url) as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) AS n FROM applications').fetchone()['n'], 0)
                self.assertEqual(connection.execute('SELECT COUNT(*) AS n FROM application_events').fetchone()['n'], 0)
            with self.assertRaisesRegex(RuntimeError, 'application_cooldown'):
                self.submit(102)

    def test_current_cooldown_changes_after_answer_cleanup(self):
        self.form = self.repo.save_form(1, 900, definition(retention_days=1, cooldown_seconds=0),
            form_id=self.form['id'], revision=1)
        with patch('applications.repository.time', SimpleNamespace(time=lambda: self.start)):
            self.submit()
        with patch('applications.repository.time', SimpleNamespace(time=lambda: self.start + 86401)):
            self.repo.purge_expired()
            self.form = self.repo.save_form(1, 900, definition(retention_days=1, cooldown_seconds=2592000),
                form_id=self.form['id'], revision=2)
            with self.assertRaisesRegex(RuntimeError, 'application_cooldown'):
                self.submit(101)
            self.form = self.repo.save_form(1, 900, definition(retention_days=1, cooldown_seconds=1),
                form_id=self.form['id'], revision=3)
            latest = self.submit(102)
            with transaction(self.url) as connection:
                self.assertEqual(connection.execute('SELECT submitted_at FROM application_cooldowns').fetchone()['submitted_at'], latest['created_at'])

    def test_evidence_isolated_by_guild_form_author_and_expires_at_maximum(self):
        with patch('applications.repository.time', SimpleNamespace(time=lambda: self.start)):
            self.submit()
            other = self.repo.save_form(1, 900, definition())
            self.submit(101, form=other)
            self.submit(102, author=11)
            GuildSettingsRepository(self.url).set_module(2, 'applications', enabled=True)
            foreign = self.repo.save_form(2, 900, definition())
            self.submit(103, form=foreign, guild=2)
        GuildSettingsRepository(self.url).set_module(1, 'applications', enabled=False)
        self.repo.purge_expired(now=self.start + 2591999)
        with transaction(self.url) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) AS n FROM application_cooldowns').fetchone()['n'], 4)
        self.repo.purge_expired(now=self.start + 2592000)
        with transaction(self.url) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) AS n FROM application_cooldowns').fetchone()['n'], 0)
        GuildSettingsRepository(self.url).set_module(1, 'applications', enabled=True)
        with patch('applications.repository.time', SimpleNamespace(time=lambda: self.start + 2592000)):
            self.submit(104)

    def test_concurrent_expired_cleanup_and_new_intake_preserve_latest_evidence(self):
        with patch('applications.repository.time', SimpleNamespace(time=lambda: self.start)):
            self.submit()
        now = self.start + 2592001
        gate = Barrier(3)
        def submit():
            gate.wait(timeout=10)
            return self.submit(101)
        def purge():
            gate.wait(timeout=10)
            return self.repo.purge_expired()
        with patch('applications.repository.time', SimpleNamespace(time=lambda: now)):
            with ThreadPoolExecutor(2) as pool:
                submitted, purged = pool.submit(submit), pool.submit(purge)
                gate.wait(timeout=10)
                item = submitted.result(timeout=20)
                purged.result(timeout=20)
        with transaction(self.url) as connection:
            self.assertEqual(connection.execute('SELECT submitted_at FROM application_cooldowns').fetchone()['submitted_at'], now)
        self.assertEqual(item['created_at'], now)
        self.assertEqual(len(self.repo.items(1)), 1)

    def test_concurrent_submissions_do_not_overwrite_one_cooldown(self):
        gate = Barrier(3)
        def submit(interaction):
            gate.wait(timeout=10)
            try:
                return self.submit(interaction)['id']
            except RuntimeError:
                return None
        with ThreadPoolExecutor(2) as pool:
            results = [pool.submit(submit, key) for key in (100, 101)]
            gate.wait(timeout=10)
            self.assertEqual(sum(result.result(timeout=20) is not None for result in results), 1)
        with transaction(self.url) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) AS n FROM application_cooldowns').fetchone()['n'], 1)

    def test_upgrade_backfills_latest_remaining_submissions_and_is_idempotent(self):
        with temporary_database(migrate=False) as url, tempfile.TemporaryDirectory() as directory:
            old = Path(directory)
            for source in sorted(MIGRATIONS.glob('*.sql'))[:2]:
                shutil.copy2(source, old / source.name)
            apply(url, old)
            with transaction(url) as connection:
                now = connection.execute('SELECT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::BIGINT AS now').fetchone()['now']
                form = connection.execute('INSERT INTO application_forms(guild_id,config_json,created_at,updated_at) VALUES(1,%s,%s,%s) RETURNING id',
                    (json.dumps(definition()), now, now)).fetchone()['id']
                for key, author, created in ((100, 10, now-100), (101, 10, now-50), (102, 11, now-2592001)):
                    connection.execute("INSERT INTO applications(guild_id,form_id,author_id,interaction_id,snapshot_json,answers_json,status,created_at,updated_at,expires_at) VALUES(1,%s,%s,%s,'{}','{}','approved',%s,%s,%s)",
                        (form, author, key, created, created, now+1000))
            apply(url)
            self.assertEqual(apply(url), {'applied': []})
            with transaction(url) as connection:
                rows = connection.execute('SELECT guild_id,form_id,author_id,submitted_at FROM application_cooldowns').fetchall()
                self.assertEqual(rows, [dict(guild_id=1, form_id=form, author_id=10, submitted_at=now-50)])


if __name__ == '__main__':
    unittest.main()
