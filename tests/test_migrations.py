"""PostgreSQL migration invariants; SQLite data conversion is intentionally retired."""
import tempfile
import unittest
from pathlib import Path

import psycopg

from database import SchemaNotReady, connect, require_current
from database.migrations import MIGRATIONS, apply, load
from database.testing import temporary_database


class MigrationTests(unittest.TestCase):
    def test_social_delivery_budget_upgrade_preserves_receipts_and_accounts_old_attempts(self):
        for version, name, checksum, source in load()[:8]:
            self.sql(source, name)
        apply(self.url, self.directory)
        with connect(self.url) as connection:
            for identifier, state, attempts in ((1, 'sent', 2), (2, 'failed', 8), (3, 'pending', 3)):
                connection.execute("""INSERT INTO social_deliveries
                    (subscription_id,event_key,discord_channel_id,discord_message_id,state,
                     created_at,updated_at,attempts,next_attempt_at,last_error)
                    VALUES(%s,'youtube:video:upgrade',10,%s,%s,100,200,%s,300,'preserved error')""",
                    (identifier, 900 if state == 'sent' else None, state, attempts))
            before = connection.execute('SELECT * FROM social_deliveries ORDER BY id').fetchall()
        self.assertEqual(apply(self.url), {'applied': [row[1] for row in load()[8:]]})
        with connect(self.url) as connection:
            expected = [{**row, 'dispatch_accounted_attempts': row['attempts']} for row in before]
            self.assertEqual(connection.execute('SELECT * FROM social_deliveries ORDER BY id').fetchall(), expected)
        self.assertEqual(apply(self.url), {'applied': []})
        with connect(self.url) as connection:
            self.assertEqual(connection.execute('SELECT * FROM social_deliveries ORDER BY id').fetchall(), expected)
        require_current(self.url)

    def test_initial_baseline_contains_final_defaults_and_vote_constraint(self):
        migrations = load()
        self.assertEqual([row[0] for row in migrations], list(range(1, len(migrations) + 1)))
        self.assertEqual(migrations[0][:2], (1, '0001_initial.sql'))
        self.sql((MIGRATIONS / '0001_initial.sql').read_text(encoding='utf-8'), '0001_initial.sql')
        self.assertEqual(apply(self.url, self.directory), {'applied': ['0001_initial.sql']})
        with connect(self.url) as c:
            item = c.execute("INSERT INTO suggestions(guild_id,channel_id,author_id,answers_json,created_at,updated_at) VALUES(1,2,3,'{}',1,1) RETURNING *").fetchone()
            self.assertEqual(item['review_reason'], '')
            self.assertEqual(item['category'], '')
            self.assertEqual(item['tags_json'], '[]')
            for name in ('discussion_thread_id', 'implemented_at', 'merged_into', 'expires_at'):
                self.assertIsNone(item[name])
            for user, value in enumerate((-1, 0, 1), start=10):
                c.execute('INSERT INTO suggestion_votes VALUES(%s,%s,%s,1,1)', (item['id'], user, value))
            c.execute("INSERT INTO insights_observers(guild_id,owner,revision,last_seen) VALUES(1,'baseline',1,100)")
            self.assertEqual(c.execute('SELECT started_at FROM insights_observers').fetchone()['started_at'], 0)
        with self.assertRaises(psycopg.errors.CheckViolation), connect(self.url) as c:
            c.execute('INSERT INTO suggestion_votes VALUES(%s,20,2,1,1)', (item['id'],))
        self.assertEqual(apply(self.url, self.directory), {'applied': []})
        self.assertEqual(apply(self.url), {'applied': [row[1] for row in migrations[1:]]})
        require_current(self.url)

    def test_longer_history_is_rejected_without_resetting_data(self):
        apply(self.url)
        with connect(self.url) as c:
            c.execute("INSERT INTO app_metadata VALUES('preserved','keep')")
            for version in range(len(load()) + 1, len(load()) + 11):
                c.execute('INSERT INTO schema_migrations VALUES(%s,%s,%s,1)',
                    (version, f'{version:04d}_previous.sql', 'previous-checksum'))
            before = c.execute('SELECT * FROM schema_migrations ORDER BY version').fetchall()
        with self.assertRaisesRegex(ValueError, 'Applied migration history differs'):
            apply(self.url)
        with self.assertRaises(SchemaNotReady):
            require_current(self.url)
        with connect(self.url) as c:
            self.assertEqual(c.execute('SELECT * FROM schema_migrations ORDER BY version').fetchall(), before)
            self.assertEqual(c.execute('SELECT value FROM app_metadata').fetchone()['value'], 'keep')

    def test_reaction_role_expiry_upgrade_preserves_nonempty_initial_schema(self):
        self.sql((MIGRATIONS / '0001_initial.sql').read_text(encoding='utf-8'), '0001_initial.sql')
        apply(self.url, self.directory)
        with connect(self.url) as c:
            c.execute("INSERT INTO app_metadata VALUES('preserved','keep')")
            row = c.execute("""INSERT INTO reaction_role_schedules(guild_id,message_config_id,mapping_id,user_id,kind,due_at,created_at)
                VALUES(1,2,3,4,'temp_role',500,100) RETURNING *""").fetchone()
            self.assertNotIn('role_id', row)
        pending = [entry[1] for entry in load()[1:]]
        self.assertEqual(apply(self.url), {'applied': pending})
        with connect(self.url) as c:
            upgraded = c.execute('SELECT * FROM reaction_role_schedules WHERE id=%s', (row['id'],)).fetchone()
            self.assertEqual(upgraded, {**row, 'role_id': None, 'scheduled_for': 500,
                'selection_generation': None, 'cleanup_only': False, 'state': 'failed', 'completed_at': 100,
                'last_error': 'Selection generation unavailable; reconciliation required'})
            c.execute('UPDATE reaction_role_schedules SET role_id=20 WHERE id=%s', (row['id'],))
            self.assertEqual(c.execute('SELECT value FROM app_metadata').fetchone()['value'], 'keep')
        self.assertEqual(apply(self.url), {'applied': []})
        require_current(self.url)
        with connect(self.url) as c:
            self.assertEqual(c.execute('SELECT role_id FROM reaction_role_schedules WHERE id=%s', (row['id'],)).fetchone()['role_id'], 20)

    def test_schedule_identity_upgrade_preserves_deadlines_and_quarantines_ambiguous_retries(self):
        for version, name, checksum, source in load()[:3]:
            self.sql(source, name)
        apply(self.url, self.directory)
        with connect(self.url) as c:
            config_id = c.execute("""INSERT INTO reaction_role_messages_v2(guild_id,channel_id,name,source,behavior_type,created_at,updated_at,self_destruct_at)
                VALUES(1,10,'Keep future deadline','bot','temp',1,1,1000) RETURNING id""").fetchone()['id']
            mapping_id = c.execute("""INSERT INTO reaction_role_mappings_v2(message_config_id,emoji_key,emoji_display,role_id,position)
                VALUES(%s,'unicode:😀','😀',20,0) RETURNING id""", (config_id,)).fetchone()['id']
            c.execute("INSERT INTO reaction_role_assignments VALUES(%s,%s,30,20,'active',1000,1,1)", (config_id,mapping_id))
            retry_id = c.execute("""INSERT INTO reaction_role_schedules(guild_id,message_config_id,mapping_id,user_id,kind,due_at,created_at,state,attempts)
                VALUES(1,%s,%s,30,'temp_role',130,1,'retry',1) RETURNING id""", (config_id,mapping_id)).fetchone()['id']
            self_retry_id = c.execute("""INSERT INTO reaction_role_schedules(guild_id,message_config_id,kind,due_at,created_at,state,attempts)
                VALUES(1,%s,'self_destruct',130,1,'retry',1) RETURNING id""", (config_id,)).fetchone()['id']
            pending_id = c.execute("""INSERT INTO reaction_role_schedules(guild_id,kind,due_at,created_at,state,attempts)
                VALUES(2,'self_destruct',500,1,'pending',0) RETURNING id""").fetchone()['id']
            processing_id = c.execute("""INSERT INTO reaction_role_schedules(guild_id,kind,due_at,created_at,state,attempts)
                VALUES(2,'self_destruct',600,1,'processing',1) RETURNING id""").fetchone()['id']
            old_id = c.execute("""INSERT INTO reaction_role_schedules(guild_id,user_id,role_id,kind,due_at,created_at)
                VALUES(3,30,20,'temp_role',200,1) RETURNING id""").fetchone()['id']
            newest_id = c.execute("""INSERT INTO reaction_role_schedules(guild_id,user_id,role_id,kind,due_at,created_at)
                VALUES(3,30,20,'temp_role',100,2) RETURNING id""").fetchone()['id']
        for version, name, checksum, source in load()[3:4]:
            self.sql(source, name)
        self.assertEqual(apply(self.url, self.directory), {'applied': [row[1] for row in load()[3:4]]})
        with connect(self.url) as c:
            rows = {row['id']: row for row in c.execute('SELECT * FROM reaction_role_schedules').fetchall()}
            for identifier in (retry_id, self_retry_id):
                self.assertEqual(rows[identifier]['state'], 'failed')
                self.assertIsNone(rows[identifier]['scheduled_for'])
                self.assertIn('reconciliation required', rows[identifier]['last_error'])
                self.assertEqual(rows[identifier]['due_at'], 130)
            self.assertEqual(rows[retry_id]['role_id'], 20)
            self.assertEqual(rows[pending_id]['scheduled_for'], 500)
            self.assertEqual(rows[processing_id]['scheduled_for'], 600)
            self.assertEqual(rows[old_id]['state'], 'done')
            self.assertIn('Superseded', rows[old_id]['last_error'])
            self.assertEqual(rows[newest_id]['state'], 'pending')
            self.assertEqual(rows[newest_id]['scheduled_for'], 100)
            self.assertEqual(c.execute('SELECT expires_at FROM reaction_role_assignments').fetchone()['expires_at'], 1000)
            self.assertEqual(c.execute('SELECT self_destruct_at FROM reaction_role_messages_v2').fetchone()['self_destruct_at'], 1000)
        self.assertEqual(apply(self.url), {'applied': [row[1] for row in load()[4:]]})
        require_current(self.url)

    def test_selection_generation_upgrade_restores_only_proven_assignment_cleanup(self):
        for version, name, checksum, source in load()[:5]:
            self.sql(source, name)
        apply(self.url, self.directory)
        with connect(self.url) as c:
            config = c.execute("""INSERT INTO reaction_role_messages_v2(guild_id,channel_id,name,source,behavior_type,created_at,updated_at)
                VALUES(1,10,'Original','bot','temp',1,1) RETURNING id""").fetchone()['id']
            mapping = c.execute("""INSERT INTO reaction_role_mappings_v2(message_config_id,emoji_key,emoji_display,role_id,position)
                VALUES(%s,'unicode:😀','😀',20,0) RETURNING id""", (config,)).fetchone()['id']
            c.execute("INSERT INTO reaction_role_assignments VALUES(%s,%s,30,20,'active',100,1,1)", (config,mapping))
            attached = c.execute("""INSERT INTO reaction_role_schedules(guild_id,message_config_id,mapping_id,user_id,kind,scheduled_for,due_at,role_id,created_at,state,last_error,completed_at)
                VALUES(1,%s,%s,30,'temp_role',100,100,20,1,'done','Superseded by a newer Reaction Role selection',1) RETURNING id""", (config,mapping)).fetchone()['id']
            detached = c.execute("""INSERT INTO reaction_role_schedules(guild_id,message_config_id,user_id,kind,scheduled_for,due_at,role_id,created_at)
                VALUES(1,%s,30,'temp_role',200,200,20,1) RETURNING id""", (config,)).fetchone()['id']
            c.execute("INSERT INTO reaction_role_outbox(guild_id,action,payload_json,created_at) VALUES(1,'clear_selection','{}',1)")
        self.assertEqual(apply(self.url), {'applied': [row[1] for row in load()[5:]]})
        with connect(self.url) as c:
            current = c.execute('SELECT generation FROM reaction_role_assignments').fetchone()['generation']
            jobs = {row['id']:row for row in c.execute('SELECT * FROM reaction_role_schedules').fetchall()}
            self.assertEqual(jobs[attached]['selection_generation'], current)
            self.assertTrue(jobs[attached]['cleanup_only'])
            self.assertEqual(jobs[attached]['state'], 'pending')
            self.assertIsNone(jobs[attached]['completed_at'])
            self.assertIsNone(jobs[detached]['selection_generation'])
            self.assertEqual(jobs[detached]['state'], 'failed')
            self.assertIn('reconciliation required', jobs[detached]['last_error'])
            old_cleanup = c.execute('SELECT state,last_error FROM reaction_role_outbox').fetchone()
            self.assertEqual(old_cleanup['state'], 'failed')
            self.assertIn('reconciliation required', old_cleanup['last_error'])
        self.assertEqual(apply(self.url), {'applied': []})
        require_current(self.url)

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
        from applications.repository import ApplicationRepository
        from appeals.repository import AppealRepository
        from scheduling.repository import ScheduleRepository
        from starboard.repository import StarboardRepository
        from giveaways.repository import GiveawayRepository
        from insights.repository import InsightsRepository
        repositories = (CommunityRepository, DashboardRepository, EngagementRepository, GuildSettingsRepository,
            ModerationRepository, ReactionRoleRepository, SocialRepository, SuggestionRepository, TicketRepository, ApplicationRepository, AppealRepository, ScheduleRepository,StarboardRepository,GiveawayRepository,InsightsRepository)
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
