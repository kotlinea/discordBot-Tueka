from community import CommunityRepository
from db_support import prepare_database, set_fixture_version
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from moderation.models import default_rule, validate_rule
from migrate import apply
from moderation import ModerationRepository


OLD_TABLES = {'automod_rules', 'automod_events', 'automod_migrations', 'moderation_migrations'}
OLD_COLUMNS = {'guild_users': {'warn'}, 'moderation_cases': {'rule_id', 'automod_event_id'},
               'moderation_points': {'rule_id', 'automod_event_id'}, 'moderation_rules': {'legacy_rule_id'}}


class ModerationRemovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'test.db'
        self.backups = self.root / 'backups'

    def retained(self):
        with closing(sqlite3.connect(self.db)) as connection:
            names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            result = {}
            for name in names:
                if name in OLD_TABLES | {'schema_migrations'}:
                    continue
                columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{name}")') if row[1] not in OLD_COLUMNS.get(name, set())]
                fields = ','.join('"' + field + '"' for field in columns)
                result[name] = connection.execute(f'SELECT {fields} FROM "{name}" ORDER BY rowid').fetchall()
            return result

    def assert_clean(self):
        with closing(sqlite3.connect(self.db)) as connection:
            names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertFalse(names & OLD_TABLES)
            self.assertFalse(any(name.startswith('_p1_copy_') for name in names))
            for table, forbidden in OLD_COLUMNS.items():
                self.assertFalse(forbidden & {row[1] for row in connection.execute(f'PRAGMA table_info({table})')})
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def seed(self, mixed):
        prepare_database(self.db)
        storage = ModerationRepository(self.db)
        CommunityRepository(storage.database_path).add_xp(1, 2, 999)
        rule = storage.save_moderation_rule(1, validate_rule({**default_rule('keyword'), 'trigger_config': {'keywords': ['bad']}}))
        event = storage.create_moderation_event(1, family='automod', event_type='message_create', source='automod',
            reason='keep event', rule_id=rule['id'], target_user_id=2, dedupe_key='keep')
        case = storage.add_case(1, 2, 'warn', 'keep case', moderation_event_id=event, moderation_rule_id=rule['id'], points=2)
        storage.add_points(1, 2, 2, 'keep points', moderation_event_id=event, moderation_rule_id=rule['id'])
        storage.finish_moderation_event(event, [{'type': 'points', 'status': 'success', 'case_id': case}])
        storage.schedule_moderation_action(1, 2, 'unban', 1, 'keep schedule', case)
        if mixed:
            with storage._connection() as connection:
                # Rebuild the fixture using the recorded pre-removal schema, preserving current rows.
                tables = ['moderation_rules', 'guild_users', 'moderation_cases', 'moderation_points',
                          'moderation_events', 'moderation_action_results']
                columns = {}
                for table in tables:
                    columns[table] = [row[1] for row in connection.execute(f'PRAGMA table_info({table})')]
                    connection.execute(f'CREATE TEMP TABLE fixture_copy_{table} AS SELECT * FROM {table}')
                for table in reversed(tables):
                    connection.execute(f'DROP TABLE {table}')
                connection.executescript(Path('tests/fixtures/moderation_pre_p1.sql').read_text(encoding='utf-8'))
                for table in tables:
                    fields = ','.join(columns[table])
                    connection.execute(f'INSERT INTO {table}({fields}) SELECT {fields} FROM fixture_copy_{table}')
                    connection.execute(f'DROP TABLE fixture_copy_{table}')
                connection.executescript("""
                    INSERT INTO automod_rules(id,guild_id,name,trigger_type,created_at,updated_at) VALUES(50,1,'old','keyword',1,1);
                    INSERT INTO automod_events(id,guild_id,rule_id,user_id,channel_id,trigger_type,reason,mode,created_at) VALUES(50,1,50,2,3,'keyword','old','enforce',1);
                    INSERT INTO automod_migrations VALUES(1,1,1);
                    INSERT INTO moderation_migrations VALUES(1,1,1);
                    UPDATE guild_users SET warn=8;
                    UPDATE moderation_points SET rule_id=50,automod_event_id=50;
                    UPDATE moderation_cases SET rule_id=50,automod_event_id=50;
                    UPDATE moderation_rules SET legacy_rule_id=50;
                """)
        set_fixture_version(self.db, 3)
        return storage, rule, event, case

    def test_empty_database_and_restart(self):
        apply(self.db, self.backups)
        for _ in range(2):
            ModerationRepository(self.db)
            self.assert_clean()
        self.assertEqual(apply(self.db, self.backups), {'applied': [], 'snapshot': None})

    def test_mixed_and_v2_only_keep_links_points_cases_xp_and_schedules(self):
        for mixed in (True, False):
            with self.subTest(mixed=mixed):
                self.db = self.root / f'{mixed}.db'
                storage, rule, event, case = self.seed(mixed)
                before = self.retained()
                result = apply(self.db, self.backups)
                self.assertEqual(result['applied'], ['0004_remove_legacy_moderation.sql', '0005_remove_shared_settings_fallback.sql', '0006_remove_legacy_social_template.sql', '0007_current_schema.sql', '0008_job_leases.sql'])
                self.assertEqual(self.retained(), before)
                storage = ModerationRepository(self.db)
                self.assertEqual(self.retained(), before)
                self.assert_clean()
                self.assertEqual(CommunityRepository(storage.database_path).get_user(1, 2), {'xp': 999})
                self.assertEqual(storage.active_points(1, 2), 2)
                self.assertEqual(storage.recent_cases(1, 2)[0]['moderation_event_id'], event)
                self.assertEqual(storage.due_moderation_actions()[0]['case_id'], case)
                with storage._connection() as connection:
                    self.assertEqual(connection.execute('SELECT rule_id FROM moderation_events WHERE id=?', (event,)).fetchone()[0], rule['id'])
                    self.assertEqual(connection.execute('SELECT event_id,case_id FROM moderation_action_results').fetchone()[:], (event, case))
                if mixed:
                    with closing(sqlite3.connect(result['snapshot'])) as snapshot:
                        self.assertEqual(snapshot.execute('SELECT warn FROM guild_users').fetchone()[0], 8)
                        self.assertEqual(snapshot.execute('SELECT COUNT(*) FROM automod_events').fetchone()[0], 1)
                self.assertEqual(apply(self.db, self.backups), {'applied': [], 'snapshot': None})

    def test_failure_rolls_back_rebuilt_tables_and_history(self):
        self.seed(True)
        with closing(sqlite3.connect(self.db)) as connection:
            before = list(connection.iterdump())
        directory = self.root / 'failure'
        shutil.copytree('migrations', directory)
        (directory / '0009_fail.sql').write_text('INSERT INTO missing_table VALUES(1);')
        with self.assertRaises(sqlite3.OperationalError):
            apply(self.db, self.backups, directory)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(list(connection.iterdump()), before)
