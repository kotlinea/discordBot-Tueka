import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from database import BUSY_TIMEOUT_MS, SchemaNotReady, readonly, transaction
from db_support import set_fixture_version
from migrate import apply
from reaction_roles import ReactionRoleRepository
from guild_settings import GuildSettingsRepository
from suggestions import SuggestionRepository
from ticketing import TicketRepository
from dashboard.repository import DashboardRepository
from community import CommunityRepository
from moderation import ModerationRepository
from social import SocialRepository
from engagement import EngagementRepository


REPOSITORIES = (ModerationRepository, SocialRepository, EngagementRepository, TicketRepository, ReactionRoleRepository, SuggestionRepository, DashboardRepository, GuildSettingsRepository, CommunityRepository)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'test.db'

    def dump(self):
        with closing(readonly(self.db)) as connection:
            return list(connection.iterdump())

    def test_missing_database_is_rejected_without_creating_files(self):
        path = self.root / 'missing' / 'test.db'
        for repository in REPOSITORIES:
            with self.subTest(repository=repository.__name__):
                with self.assertRaisesRegex(SchemaNotReady, 'migrate.py'):
                    repository(path)
                self.assertFalse(path.parent.exists())

    def test_unversioned_pending_and_changed_history_do_not_modify_data(self):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute('CREATE TABLE keep(value TEXT)')
            connection.execute("INSERT INTO keep VALUES('preserved')")
            connection.commit()
        for condition in ('unversioned', 'pending', 'changed'):
            if condition == 'pending':
                apply(self.db, self.root / 'backups')
                set_fixture_version(self.db, 6)
            elif condition == 'changed':
                apply(self.db, self.root / 'backups')
                with transaction(self.db) as connection:
                    connection.execute("UPDATE schema_migrations SET checksum='changed' WHERE version=7")
            before = self.dump()
            for repository in REPOSITORIES:
                with self.subTest(condition=condition, repository=repository.__name__):
                    with self.assertRaises(SchemaNotReady):
                        repository(self.db)
                    self.assertEqual(self.dump(), before)

    def test_explicit_migration_boots_all_repositories_with_identical_connection_policy(self):
        apply(self.db, self.root / 'backups')
        before = self.dump()
        for _ in range(2):
            for repository in REPOSITORIES:
                instance = repository(self.db)
                manager = instance.connection if repository is ReactionRoleRepository else instance._connection
                with manager() as connection:
                    self.assertEqual(connection.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
                    self.assertEqual(connection.execute('PRAGMA foreign_keys').fetchone()[0], 1)
                    self.assertEqual(connection.execute('PRAGMA busy_timeout').fetchone()[0], BUSY_TIMEOUT_MS)
            self.assertEqual(self.dump(), before)

    def test_transaction_commits_and_rolls_back_partial_work(self):
        apply(self.db, self.root / 'backups')
        with transaction(self.db) as connection:
            connection.execute("INSERT INTO app_metadata VALUES('committed','keep')")
        before = self.dump()
        with self.assertRaises(sqlite3.IntegrityError):
            with transaction(self.db) as connection:
                connection.execute("INSERT INTO app_metadata VALUES('partial','discard')")
                connection.execute("INSERT INTO app_metadata VALUES('committed','duplicate')")
        self.assertEqual(self.dump(), before)

        with self.assertRaises(KeyboardInterrupt):
            with transaction(self.db) as connection:
                connection.execute("INSERT INTO app_metadata VALUES('interrupt','discard')")
                raise KeyboardInterrupt()
        self.assertEqual(self.dump(), before)

    def test_previous_v2_missing_columns_are_added_by_cli(self):
        apply(self.db, self.root / 'backups')
        with transaction(self.db) as connection:
            connection.execute("INSERT INTO social_events(provider,event_key,account_id,payload_json,received_at) VALUES('youtube','keep','UC1','{}',1)")
            connection.execute('DROP INDEX idx_social_events_job_claim')
            connection.execute('ALTER TABLE social_events DROP COLUMN available_at')
            connection.execute('ALTER TABLE ticket_feedback DROP COLUMN answers_encrypted_json')
            connection.execute('ALTER TABLE tickets_v2 DROP COLUMN notes_thread_id')
        set_fixture_version(self.db, 6)
        with self.assertRaises(SchemaNotReady):
            GuildSettingsRepository(self.db)
        result = apply(self.db, self.root / 'backups')
        self.assertEqual(result['applied'], ['0007_current_schema.sql', '0008_job_leases.sql'])
        with closing(readonly(self.db)) as connection:
            self.assertEqual(connection.execute('SELECT event_key,available_at FROM social_events').fetchone(), ('keep', 0))
            self.assertIn('notes_thread_id', {row[1] for row in connection.execute('PRAGMA table_info(tickets_v2)')})
            self.assertIn('answers_encrypted_json', {row[1] for row in connection.execute('PRAGMA table_info(ticket_feedback)')})
        for repository in REPOSITORIES:
            repository(self.db)
