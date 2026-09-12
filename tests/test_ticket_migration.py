from db_support import prepare_database, set_fixture_version
import asyncio
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
from cryptography.fernet import Fernet
from discord.ext import commands

from cogs.community import CommunityCog
from cogs.tickets import TicketsCog
from migrate import apply
from storage import GuildStorage
from ticketing import TicketRepository, TicketService, TranscriptStorage


class TicketRemovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'test.db'
        self.backups = self.root / 'backups'

    def contents(self):
        with closing(sqlite3.connect(self.db)) as connection:
            names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            return {name: connection.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall()
                    for name in names if name not in {'schema_migrations', 'support_tickets', 'ticket_migrations'}}

    def assert_no_legacy(self):
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT name FROM sqlite_master WHERE name IN ('support_tickets','ticket_migrations')").fetchall(), [])
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_empty_database_and_runtime_restart_do_not_restore_legacy(self):
        apply(self.db, self.backups)
        for _ in range(2):
            GuildStorage(self.db)
            repository = TicketRepository(self.db)
            self.assertFalse(repository.settings(1)['enabled'])
            self.assertEqual(repository.panels(1), [])
            self.assert_no_legacy()
        self.assertEqual(apply(self.db, self.backups), {'applied': [], 'snapshot': None})

    def test_mixed_database_upgrade_preserves_v2_blobs_queues_and_snapshot(self):
        # Reproduce the immediately preceding numbered schema before applying 0002.
        previous = self.root / 'previous'
        previous.mkdir()
        shutil.copyfile('migrations/0001_suggestions.sql', previous / '0001_suggestions.sql')
        prepare_database(self.db)
        GuildStorage(self.db)
        repository = TicketRepository(self.db)
        blobs = TranscriptStorage(self.root / 'blobs', Fernet.generate_key().decode('ascii'))
        service = TicketService(repository, blobs)
        repository.save_settings(1, {'enabled': True, 'open_limit': 5})
        team = repository.save_team(1, {'name': 'Staff', 'role_ids': [500]})
        bundle = repository.save_panel_bundle(1, {
            'panel': {'name': 'Support', 'mode': 'channel', 'category_id': 100, 'team_id': team['id']},
            'deployment': {'name': 'Entry', 'channel_id': 300, 'title': 'Help', 'description': 'Support'},
        })
        panel = bundle['panel']
        closed, _ = service.reserve(1, panel['id'], 10, 'closed', set())
        closed = repository.activate_ticket(closed['id'], 201, 100)
        service.record_message(closed, 900, 10, 'member', 'retained private content', [])
        closed, transcript = asyncio.run(service.close(closed['id'], 99, 'resolved'))
        active, _ = service.reserve(1, panel['id'], 11, 'open', set())
        active = repository.activate_ticket(active['id'], 202, 100)
        repository.set_awaiting_user(active['id'], 100)
        repository.queue_outbox(active['id'], 'auto_close', 99, {'reason': 'scheduled'})
        repository.set_schedule(active['id'], 'no_user_reply', 1)
        with closing(sqlite3.connect(self.db)) as connection:
            connection.executescript("""
                CREATE TABLE support_tickets(channel_id INTEGER PRIMARY KEY,guild_id INTEGER,opener_id INTEGER,status TEXT,created_at INTEGER,closed_at INTEGER,closed_by INTEGER,transcript_json TEXT);
                INSERT INTO support_tickets VALUES(999,1,12,'closed',1,2,99,'[{"content":"V1 only"}]');
                CREATE TABLE ticket_migrations(name TEXT PRIMARY KEY,completed_at INTEGER);
                INSERT INTO ticket_migrations VALUES('legacy_ticket_v2',1);
                INSERT INTO guild_modules(guild_id,module_id,enabled,settings_json) VALUES(2,'tickets',1,'{"ticket_category_id":123}');
            """)
        # A runtime restart must neither migrate the V1 ticket nor import its settings.
        repository = TicketRepository(self.db)
        self.assertIsNone(repository.ticket_for_container(999))
        self.assertFalse(repository.settings(2)['enabled'])
        set_fixture_version(self.db, 1)
        before = self.contents()
        blob_file = self.root / 'blobs' / transcript['object_key']
        encrypted = blob_file.read_bytes()
        result = apply(self.db, self.backups)
        self.assertEqual(result['applied'], ['0002_remove_legacy_tickets.sql', '0003_remove_legacy_reaction_roles.sql', '0004_remove_legacy_moderation.sql', '0005_remove_shared_settings_fallback.sql', '0006_remove_legacy_social_template.sql', '0007_current_schema.sql'])
        with closing(sqlite3.connect(result['snapshot'])) as snapshot:
            self.assertIn('V1 only', snapshot.execute('SELECT transcript_json FROM support_tickets').fetchone()[0])
            self.assertEqual(snapshot.execute('SELECT COUNT(*) FROM ticket_migrations').fetchone()[0], 1)
        GuildStorage(self.db)
        repository = TicketRepository(self.db)
        self.assert_no_legacy()
        self.assertEqual(self.contents(), before)
        self.assertEqual(blob_file.read_bytes(), encrypted)
        payload = asyncio.run(blobs.load(transcript['backend'], transcript['object_key'], transcript['content_hash']))
        self.assertEqual(payload['messages'][0]['content'], 'retained private content')
        self.assertEqual(repository.ticket(active['id'])['status'], 'awaiting_user')
        self.assertEqual(repository.claim_outbox('after-restart')[0]['ticket_id'], active['id'])
        self.assertEqual(repository.due_schedules()[0]['ticket_id'], active['id'])
        self.assertEqual(apply(self.db, self.backups), {'applied': [], 'snapshot': None})

    def test_legacy_button_is_ignored_and_current_button_is_dispatched(self):
        cog = TicketsCog.__new__(TicketsCog)
        cog.show_open = AsyncMock()
        interaction = SimpleNamespace(type=discord.InteractionType.component,
                                      data={'custom_id': 'tueka-ticket:create'}, guild=SimpleNamespace(id=1))
        asyncio.run(cog.on_interaction(interaction))
        cog.show_open.assert_not_awaited()
        interaction.data['custom_id'] = 'tueka-ticket:open:42'
        asyncio.run(cog.on_interaction(interaction))
        cog.show_open.assert_awaited_once_with(interaction, 42)
        self.assertEqual(CommunityCog.__cog_app_commands__, [])
        self.assertIn('open', {command.name for command in cog.ticket.commands})

    def test_existing_v2_only_database_does_not_require_legacy_tables(self):
        prepare_database(self.db)
        repository = TicketRepository(self.db)
        settings = repository.save_settings(8, {'enabled': True, 'open_limit': 4})
        team = repository.save_team(8, {'name': 'Team', 'role_ids': [80]})
        panel = repository.save_panel(8, {'name': 'Thread', 'mode': 'private_thread', 'thread_parent_channel_id': 81, 'staff_notification_channel_id': 84, 'team_id': team['id']})
        ticket = repository.reserve_ticket(8, panel['id'], 82, 'thread', {})
        ticket = repository.activate_ticket(ticket['id'], 83, 81)
        set_fixture_version(self.db, 1)
        apply(self.db, self.backups)
        reopened = TicketRepository(self.db)
        self.assertEqual(reopened.settings(8), settings)
        self.assertEqual(reopened.ticket(ticket['id']), ticket)
        self.assertEqual(reopened.panels(8), [panel])
        self.assert_no_legacy()

    def test_failure_after_legacy_drop_restores_tables_data_and_history(self):
        prepare_database(self.db)
        repository = TicketRepository(self.db)
        saved = repository.save_settings(1, {'enabled': True})
        with closing(sqlite3.connect(self.db)) as connection:
            connection.executescript("CREATE TABLE support_tickets(id INTEGER PRIMARY KEY,transcript_json TEXT); INSERT INTO support_tickets VALUES(1,'private'); CREATE TABLE ticket_migrations(name TEXT); DROP TABLE schema_migrations;")
        directory = self.root / 'failing'
        directory.mkdir()
        for source in Path('migrations').glob('*.sql'):
            shutil.copyfile(source, directory / source.name)
        (directory / '0008_fail.sql').write_text('INSERT INTO missing_table VALUES(1);')
        with self.assertRaises(sqlite3.OperationalError):
            apply(self.db, self.backups, directory)
        self.assertEqual(repository.settings(1), saved)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('SELECT transcript_json FROM support_tickets').fetchone()[0], 'private')
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM ticket_migrations').fetchone()[0], 0)
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='schema_migrations'").fetchone())

    def test_bot_loads_current_ticket_commands_without_rollout_settings(self):
        prepare_database(self.db)
        async def load():
            async with commands.Bot(command_prefix='!', intents=discord.Intents.none()) as bot:
                bot.settings = SimpleNamespace(database_path=self.db, data_dir=self.root,
                    ticket_encryption_key=None, ticket_s3_endpoint_url=None, ticket_s3_region=None,
                    ticket_s3_bucket=None, ticket_s3_access_key_id=None, ticket_s3_secret_access_key=None,
                    ticket_s3_prefix='tickets')
                await bot.load_extension('cogs.community')
                await bot.load_extension('cogs.tickets')
                self.assertEqual({command.name for command in bot.tree.get_commands()}, {'ticket', 't'})
                self.assert_no_legacy()
        asyncio.run(load())
