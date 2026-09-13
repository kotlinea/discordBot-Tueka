"""Cross-domain contracts that must survive persistence refactors."""
import ast
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord

from cogs.audit_log import AuditLogCog
from db_support import prepare_database
from engagement import EngagementRepository
from guild_settings import GuildSettingsRepository
from moderation import ModerationRepository


class DomainBoundaryTests(unittest.TestCase):
    def test_entrypoints_services_and_adapters_do_not_execute_sql(self):
        root = Path(__file__).resolve().parents[1]
        files = list(root.glob('*.py'))
        for folder in ('cogs', 'dashboard', 'community', 'engagement', 'social',
                       'moderation', 'ticketing', 'suggestions', 'reaction_roles', 'guild_settings'):
            files.extend((root / folder).glob('*.py'))
        for path in files:
            if path.name in {'database.py', 'migrate.py', 'repository.py'}:
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertNotIn(node.func.attr, {'execute', 'executemany', 'executescript', '_connection'}, str(path))
                if isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(node.module, 'storage', str(path))

    def test_poll_votes_restart_expiry_and_message_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = prepare_database(Path(directory) / 'test.db')
            repository = EngagementRepository(path)
            repository.create_poll(100, 1, 10, 20, 'Choose', ['A', 'B'], None, None)
            repository.create_poll(200, 2, 10, 20, 'Other', ['A', 'B'], None, None)
            self.assertEqual(repository.cast_poll_vote(100, 20, 0), [1, 0])
            restarted = EngagementRepository(path)
            self.assertEqual(restarted.cast_poll_vote(100, 20, 1), [0, 1])
            self.assertEqual(restarted.cast_poll_vote(200, 20, 0), [1, 0])
            self.assertIsNone(restarted.cast_poll_vote(100, 20, 2))
            repository.create_poll(300, 1, 10, 20, 'Expired', ['A', 'B'], None, 1)
            self.assertIsNone(restarted.cast_poll_vote(300, 20, 0))
            self.assertEqual([poll['message_id'] for poll in restarted.close_expired_polls()], [300])
            self.assertEqual(restarted.close_expired_polls(), [])
            self.assertEqual(restarted.poll(100)['guild_id'], 1)
            self.assertEqual(restarted.poll(200)['guild_id'], 2)


class AuditPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_discord_audit_delivery_persists_to_moderation_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            path = prepare_database(Path(directory) / 'test.db')
            GuildSettingsRepository(path).set_module(1, 'moderation_logs', enabled=True,
                settings={'log_join': True, 'log_channel_id': 10})
            channel = MagicMock(spec=discord.TextChannel)
            channel.id = 10
            channel.send = AsyncMock()
            guild = SimpleNamespace(id=1, get_channel=lambda _: channel)
            cog = AuditLogCog(SimpleNamespace(settings=SimpleNamespace(database_path=path)))
            await cog._send(guild, 'members', '参加', discord.Color.green())
            channel.send.assert_awaited_once()
            repository = ModerationRepository(path)
            events = repository.recent_moderation_events(1)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]['source'], 'discord_audit')
            self.assertEqual(repository.recent_moderation_events(2), [])
