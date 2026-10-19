import ast
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from db_support import prepare_database
from guild_settings import GuildSettingsRepository
from moderation import ModerationRepository
from moderation.contracts import ActionFailure, GuildRef, MemberRef
from moderation.service import ModerationService


class FakePort:
    def __init__(self):
        self.calls = []
        self.permissions = {'send_messages': None, 'send_messages_in_threads': None}
        self.fail_permissions = False

    def manageable(self, actor, target, action):
        return None

    async def member_action(self, *args):
        self.calls.append(args)

    async def applied(self, *args):
        return True

    async def dm(self, *args):
        return False

    async def send(self, *args, **kwargs):
        pass

    def lockdown_snapshots(self, *args):
        return [{'channel_id': 10, 'role_id': 1, 'before': dict(self.permissions),
                 'applied': {'send_messages': False, 'send_messages_in_threads': False}}]

    async def set_overwrite(self, guild_id, channel_id, role_id, values, reason):
        if self.fail_permissions:
            raise ActionFailure('permission lost')
        self.permissions = dict(values)

    def overwrite(self, *args):
        return dict(self.permissions)


class ModerationAdapterTests(unittest.IsolatedAsyncioTestCase):
    def test_timeout_administrator_is_rejected_even_below_bot_role(self):
        from types import SimpleNamespace
        from moderation.discord_adapter import DiscordModerationAdapter
        administrator = SimpleNamespace(id=2, top_role=1, guild_permissions=SimpleNamespace(administrator=True))
        moderator = SimpleNamespace(id=3, top_role=3)
        guild = SimpleNamespace(owner_id=3, get_member=lambda identifier: administrator if identifier == 2 else moderator,
                                me=SimpleNamespace(top_role=2, guild_permissions=SimpleNamespace(moderate_members=True)))
        adapter = DiscordModerationAdapter(SimpleNamespace(get_guild=lambda identifier: guild))
        for action in ('timeout', 'untimeout'):
            self.assertIn('Administrator', adapter.manageable(MemberRef(3, 1), MemberRef(2, 1), action))
        administrator.guild_permissions.administrator = False
        self.assertIsNone(adapter.manageable(MemberRef(3, 1), MemberRef(2, 1), 'timeout'))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = prepare_database(Path(self.temp.name) / 'test.db', self.addCleanup)
        self.repository = ModerationRepository(path)
        self.port = FakePort()
        self.service = ModerationService(self.port, self.repository, GuildSettingsRepository(path))
        self.guild, self.member = GuildRef(1, 'Guild'), MemberRef(2, 1, 'User')

    async def test_case_and_temporary_ban_recovery_are_atomic_and_not_reexecuted(self):
        with patch.object(self.repository, 'add_case', side_effect=RuntimeError('database unavailable')):
            with self.assertRaises(RuntimeError):
                await self.service.apply_case(self.guild, self.member, 'tempban', 'reason', duration_minutes=2,
                                              notify=False, execution_key='request')
        self.assertEqual(len(self.port.calls), 1)
        with self.assertRaises(ActionFailure):
            await self.service.apply_case(self.guild, self.member, 'tempban', 'reason', execution_key='request')
        restarted = ModerationService(self.port, ModerationRepository(self.repository.database_url), self.service.guild_settings)
        case = await restarted.reconcile_case(self.guild, 'request')
        self.assertEqual(await restarted.reconcile_case(self.guild, 'request'), case)
        self.assertEqual(len(self.port.calls), 1)
        self.assertEqual(len(self.repository.recent_cases(1, 2)), 1)
        with self.repository._connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) AS count FROM scheduled_moderation_actions WHERE case_id=%s', (case,)).fetchone()["count"], 1)

    async def test_lockdown_intent_survives_permission_failure_and_conflicts_remain_active(self):
        self.port.fail_permissions = True
        with self.assertRaises(ActionFailure):
            await self.service.lockdown(self.guild, 'raid', 1)
        active = self.repository.active_lockdown(1)
        self.assertEqual(len(self.repository.lockdown_snapshots(active['id'])), 1)
        self.port.fail_permissions = False
        self.port.permissions = {'send_messages': True, 'send_messages_in_threads': None}
        self.assertEqual((await self.service.unlock_lockdown(self.guild))['conflicts'], 1)
        self.assertIsNotNone(self.repository.active_lockdown(1))
        self.port.permissions = {'send_messages': None, 'send_messages_in_threads': None}
        self.assertEqual((await self.service.unlock_lockdown(self.guild))['restored'], 1)
        self.assertIsNone(self.repository.active_lockdown(1))

    def test_service_has_no_discord_sdk_dependency(self):
        tree = ast.parse(Path('moderation/service.py').read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertNotIn('discord', [item.name for item in node.names])
            elif isinstance(node, ast.ImportFrom):
                self.assertFalse((node.module or '').startswith('discord'))

    async def test_lockdown_and_unlock_cannot_overlap_and_repeated_start_preserves_baseline(self):
        started, resume = asyncio.Event(), asyncio.Event()
        original = self.port.set_overwrite

        async def delayed(*args):
            started.set()
            await resume.wait()
            await original(*args)

        with patch.object(self.port, 'set_overwrite', side_effect=delayed):
            pending = asyncio.create_task(self.service.lockdown(self.guild, 'raid', 1))
            await started.wait()
            try:
                with self.assertRaises(ActionFailure):
                    await self.service.unlock_lockdown(self.guild)
            finally:
                resume.set()
            lockdown_id = await pending
        baseline = self.repository.lockdown_snapshots(lockdown_id)
        with self.assertRaises(ActionFailure):
            await self.service.lockdown(self.guild, 'again', 2)
        self.assertEqual(self.repository.lockdown_snapshots(lockdown_id), baseline)
        await self.service.unlock_lockdown(self.guild)
        self.assertEqual(self.port.permissions, baseline[0]['before'])

    async def test_unlock_database_failure_remains_recoverable_after_discord_restore(self):
        lockdown_id = await self.service.lockdown(self.guild, 'raid', 1)
        raid = self.repository.stale_raid_states(10 ** 12)[0]
        self.assertFalse(self.repository.clear_stale_raid(1, raid['last_signal_at']))
        with patch.object(self.repository, 'finish_lockdown', side_effect=RuntimeError('database unavailable')):
            with self.assertRaises(RuntimeError):
                await self.service.unlock_lockdown(self.guild)
        self.assertEqual(self.repository.active_lockdown(1)['id'], lockdown_id)
        self.assertEqual((await self.service.unlock_lockdown(self.guild))['restored'], 1)
        self.assertIsNone(self.repository.active_lockdown(1))

    async def test_expired_lockdown_owner_cannot_finalize_or_clear_successor_lease(self):
        original = self.port.set_overwrite

        async def expired(*args):
            await original(*args)
            with self.repository._connection() as c:
                c.execute("UPDATE resource_leases SET token='successor'")

        with patch.object(self.port, 'set_overwrite', side_effect=expired):
            with self.assertRaises(ActionFailure):
                await self.service.lockdown(self.guild, 'raid', 1)
        self.assertIsNotNone(self.repository.active_lockdown(1))
        with self.repository._connection() as c:
            self.assertEqual(c.execute('SELECT token FROM resource_leases').fetchone()['token'], 'successor')
            self.assertEqual(c.execute('SELECT COUNT(*) AS count FROM moderation_raid_state WHERE active=1').fetchone()["count"], 0)
