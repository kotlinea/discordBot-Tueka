"""PostgreSQL migration invariants; SQLite data conversion is intentionally retired."""
import tempfile
import unittest
from pathlib import Path

import psycopg

from database import SchemaNotReady, connect, require_current
from database.migrations import MIGRATIONS, apply, load
from database.testing import temporary_database


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.context = temporary_database(migrate=False)
        self.url = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def sql(self, source, name='0001_test.sql'):
        (self.directory / name).write_text(source, encoding='utf-8')
        return self.directory

    def seed(self):
        with connect(self.url) as c:
            c.execute('CREATE TABLE preserved(id BIGINT PRIMARY KEY, value TEXT)')
            c.execute("INSERT INTO preserved VALUES(1,'keep')")

    def test_observability_upgrade_preserves_existing_application_data(self):
        initial = MIGRATIONS / '0001_initial.sql'
        (self.directory / initial.name).write_bytes(initial.read_bytes())
        apply(self.url, self.directory)
        with connect(self.url) as c:
            c.execute("INSERT INTO app_metadata VALUES('upgrade_probe','preserved')")
            before = c.execute('SELECT version,name,checksum FROM schema_migrations').fetchall()
        self.assertEqual(apply(self.url)['applied'], ['0002_observability.sql'])
        with connect(self.url) as c:
            self.assertEqual(c.execute("SELECT value FROM app_metadata WHERE key='upgrade_probe'").fetchone()['value'], 'preserved')
            self.assertEqual(c.execute('SELECT version,name,checksum FROM schema_migrations WHERE version=1').fetchall(), before)
            self.assertEqual(c.execute('SELECT COUNT(*) AS count FROM runtime_heartbeats').fetchone()['count'], 0)
        self.assertEqual(apply(self.url), {'applied': []})

    def test_failed_ddl_preserves_original_data_and_removes_partial_history(self):
        self.seed()
        self.sql('DROP TABLE preserved; CREATE TABLE partial(id BIGINT); INSERT INTO absent VALUES(1);')
        with self.assertRaises(psycopg.errors.UndefinedTable):
            apply(self.url, self.directory)
        with connect(self.url) as c:
            self.assertEqual(c.execute('SELECT value FROM preserved').fetchone()['value'], 'keep')
            self.assertIsNone(c.execute("SELECT to_regclass('partial') AS relation").fetchone()['relation'])
            self.assertIsNone(c.execute("SELECT to_regclass('schema_migrations') AS relation").fetchone()['relation'])

    def test_transaction_and_session_control_cannot_escape_rollback(self):
        self.seed()
        for command in ('COMMIT', 'ROLLBACK', 'SET search_path=public', 'BEGIN', 'VACUUM'):
            with self.subTest(command=command):
                self.sql('DROP TABLE preserved; ' + command + ';')
                with self.assertRaises(ValueError):
                    apply(self.url, self.directory)
                with connect(self.url) as c:
                    self.assertEqual(c.execute('SELECT value FROM preserved').fetchone()['value'], 'keep')

    def test_second_migration_foreign_key_failure_is_atomic_and_retryable(self):
        self.sql('CREATE TABLE parent(id BIGINT PRIMARY KEY); CREATE TABLE child(parent_id BIGINT REFERENCES parent(id));')
        apply(self.url, self.directory)
        self.sql('INSERT INTO child VALUES(99);', '0002_child.sql')
        with self.assertRaises(psycopg.IntegrityError):
            apply(self.url, self.directory)
        with connect(self.url) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) AS count FROM schema_migrations').fetchone()['count'], 1)
            self.assertEqual(c.execute('SELECT COUNT(*) AS count FROM child').fetchone()['count'], 0)
        self.sql('INSERT INTO parent VALUES(99); INSERT INTO child VALUES(99);', '0002_child.sql')
        self.assertEqual(apply(self.url, self.directory)['applied'], ['0002_child.sql'])

    def test_native_conditional_column_addition_preserves_values(self):
        self.sql("CREATE TABLE example(id BIGINT PRIMARY KEY, existing TEXT); INSERT INTO example VALUES(1,'keep'); ALTER TABLE example ADD COLUMN IF NOT EXISTS existing TEXT DEFAULT 'replace'; ALTER TABLE example ADD COLUMN added BIGINT NOT NULL DEFAULT 7;")
        apply(self.url, self.directory)
        with connect(self.url) as c:
            self.assertEqual(c.execute('SELECT * FROM example').fetchone(), {'id': 1, 'existing': 'keep', 'added': 7})
        self.assertEqual(apply(self.url, self.directory), {'applied': []})

    def test_quoted_semicolons_and_comments_are_preserved(self):
        self.sql("-- initial comment\nCREATE TABLE example(value TEXT); /* separator ; */ INSERT INTO example VALUES('semi;quote''--text');")
        apply(self.url, self.directory)
        with connect(self.url) as c:
            self.assertEqual(c.execute('SELECT value FROM example').fetchone()['value'], "semi;quote'--text")

    def test_invalid_filenames_gaps_and_unterminated_sql_are_rejected(self):
        self.sql('CREATE TABLE example(id BIGINT);', '0002_gap.sql')
        with self.assertRaises(ValueError):
            load(self.directory)
        (self.directory / '0002_gap.sql').unlink()
        self.sql('CREATE TABLE example(id BIGINT)')
        with self.assertRaises(ValueError):
            apply(self.url, self.directory)

    def test_current_repositories_do_not_create_or_change_schema(self):
        from community import CommunityRepository
        from dashboard.repository import DashboardRepository
        from engagement import EngagementRepository
        from guild_settings import GuildSettingsRepository
        from moderation import ModerationRepository
        from reaction_roles import ReactionRoleRepository
        from social import SocialRepository
        from suggestions import SuggestionRepository
        from ticketing import TicketRepository
        repositories = (CommunityRepository, DashboardRepository, EngagementRepository, GuildSettingsRepository,
            ModerationRepository, ReactionRoleRepository, SocialRepository, SuggestionRepository, TicketRepository)
        for repository in repositories:
            with self.subTest(repository=repository.__name__), self.assertRaises(SchemaNotReady):
                repository(self.url)
        apply(self.url)
        def schema():
            with connect(self.url) as c:
                return c.execute("SELECT table_name,column_name,data_type,column_default FROM information_schema.columns WHERE table_schema=current_schema() ORDER BY table_name,ordinal_position").fetchall()
        before = schema()
        for repository in repositories:
            repository(self.url)
        self.assertEqual(schema(), before)
        require_current(self.url)
        self.assertEqual(apply(self.url), {'applied': []})

    def test_later_migration_preserves_current_domain_data(self):
        from suggestions import SuggestionRepository
        for baseline in MIGRATIONS.glob('*.sql'):
            self.sql(baseline.read_text(encoding='utf-8'), baseline.name)
        apply(self.url, self.directory)
        item = SuggestionRepository(self.url).create(1, 2, 3, {'idea': 'keep'})
        self.sql('ALTER TABLE suggestions ADD COLUMN migration_probe TEXT;', f'{len(load())+1:04d}_probe.sql')
        apply(self.url, self.directory)
        with connect(self.url) as c:
            row = c.execute('SELECT answers_json FROM suggestions WHERE id=%s', (item['id'],)).fetchone()
            self.assertIn('keep', row['answers_json'])
        with self.assertRaises(SchemaNotReady):
            require_current(self.url)
