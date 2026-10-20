"""Moderation partial-failure, sanction generation, and authoritative restore contracts."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from db_support import prepare_database
from guild_settings import GuildSettingsRepository
from jobs.runner import run_batch
from moderation import ModerationRepository
from moderation.contracts import ActionFailure, GuildRef, MemberRef
from moderation.discord_adapter import DiscordModerationAdapter
from moderation.service import ModerationService
from cogs.moderation.runtime import AutoModCog


class BoundaryPort:
    def __init__(self):
        self.actions = []
        self.banned = False
        self.ban_execution = None

    def manageable(self, actor, target, action):
        return None

    async def member_action(self, guild, user, action, reason, minutes, execution):
        self.actions.append(action)
        if action in {'ban', 'tempban'}:
            self.banned, self.ban_execution = True, execution
        elif action == 'unban':
            self.banned, self.ban_execution = False, None

    async def unban(self, guild, user, reason):
        self.actions.append('scheduled-unban')
        self.banned, self.ban_execution = False, None

    async def applied(self, guild, user, action, expires, execution, created):
        return self.banned and self.ban_execution == execution

    async def dm(self, *args):
        return False

    async def send(self, *args, **kwargs):
        pass


class ModerationActionBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.url = prepare_database(Path(directory.name) / 'moderation-boundaries', self.addCleanup)
        self.repository = ModerationRepository(self.url)
        self.settings = GuildSettingsRepository(self.url)
        self.settings.set_module(1, 'moderation', enabled=True, settings={})
        self.port = BoundaryPort()
        self.service = ModerationService(self.port, self.repository, self.settings)
        self.guild, self.member = GuildRef(1, 'Isolated'), MemberRef(2, 1, 'Target')

    def cog(self):
        cog = AutoModCog.__new__(AutoModCog)
        guild = SimpleNamespace(id=1, name='Isolated', get_member=lambda identifier:
            SimpleNamespace(id=identifier, guild=SimpleNamespace(id=1), name='Target'))
        cog.bot = SimpleNamespace(get_guild=lambda identifier: guild)
        cog.service, cog.moderation_repository, cog.guild_settings = self.service, self.repository, self.settings
        return cog

    async def expire(self, case):
        with self.repository._connection() as c:
            c.execute('UPDATE scheduled_moderation_actions SET due_at=0 WHERE case_id=%s', (case,))
        await run_batch(self.repository.schedule_jobs, 'isolated-expiry', self.cog()._expire_moderation_action, limit=1)

    async def test_old_tempban_expiry_preserves_new_permanent_ban(self):
        case = await self.service.apply_case(self.guild, self.member, 'tempban', 'old',
            duration_minutes=1, notify=False, execution_key='old')
        await self.service.apply_case(self.guild, self.member, 'unban', 'early release',
            notify=False, execution_key='early-release')
        await self.service.apply_case(self.guild, self.member, 'ban', 'new permanent decision',
            notify=False, execution_key='new-permanent')
        await self.expire(case)
        self.assertTrue(self.port.banned, 'A superseded temporary ban must not undo a newer permanent ban')
        self.assertNotIn('scheduled-unban', self.port.actions)

    async def test_tempban_expiry_requires_current_execution_evidence(self):
        case = await self.service.apply_case(self.guild, self.member, 'tempban', 'temporary',
            duration_minutes=1, notify=False, execution_key='temp')
        self.port.ban_execution = 'human-replacement'
        await self.expire(case)
        self.assertTrue(self.port.banned)
        self.assertNotIn('scheduled-unban', self.port.actions)

    async def test_unchanged_tempban_expires_once(self):
        case = await self.service.apply_case(self.guild, self.member, 'tempban', 'temporary',
            duration_minutes=1, notify=False, execution_key='temp')
        await self.expire(case)
        await self.expire(case)
        self.assertFalse(self.port.banned)
        self.assertEqual(self.port.actions.count('scheduled-unban'), 1)

    async def test_uncertain_tempban_evidence_leaves_failed_job_without_unban(self):
        case = await self.service.apply_case(self.guild, self.member, 'tempban', 'temporary',
            duration_minutes=1, notify=False, execution_key='temp')
        self.port.applied = AsyncMock(return_value=None)
        await self.expire(case)
        self.assertTrue(self.port.banned)
        with self.repository._connection() as c:
            self.assertEqual(c.execute('SELECT status FROM scheduled_moderation_actions WHERE case_id=%s', (case,)).fetchone()['status'], 'failed')

    async def test_member_action_cannot_overtake_expiry_evidence_lookup(self):
        case = await self.service.apply_case(self.guild, self.member, 'tempban', 'temporary',
            duration_minutes=1, notify=False, execution_key='temp')
        reached, release = asyncio.Event(), asyncio.Event()
        original = self.port.applied
        async def wait_for_evidence(*args):
            reached.set()
            await release.wait()
            return await original(*args)
        self.port.applied = wait_for_evidence
        expiry = asyncio.create_task(self.expire(case))
        await asyncio.wait_for(reached.wait(), 5)
        try:
            with self.assertRaises(ActionFailure):
                await self.service.apply_case(self.guild, self.member, 'ban', 'new ban', notify=False, execution_key='new')
        finally:
            release.set()
        await expiry
        self.assertFalse(self.port.banned)
        self.assertEqual(self.port.actions, ['tempban', 'scheduled-unban'])

    async def test_points_and_case_roll_back_together_when_case_insert_fails(self):
        self.settings.set_module(1, 'infractions', enabled=True,
            settings={'point_thresholds': [{'points': 1, 'action': {'type': 'ban'}}]})
        # A real SQL failure at the Case insert, rather than replacing a public helper,
        # keeps this fault boundary valid when atomic repository helpers are introduced.
        with self.repository._connection() as c:
            c.execute("ALTER TABLE moderation_cases ADD CONSTRAINT isolated_reject_case CHECK(reason <> 'reject-case')")
        with self.assertRaises(Exception):
            await self.service.warn(self.guild, self.member, 'reject-case', 3, notify=False)
        self.assertEqual(self.repository.active_points(1, 2), 0)
        self.assertEqual(self.repository.recent_cases(1, 2), [])
        await self.service.warn(self.guild, self.member, 'retry', 3, notify=False)
        await run_batch(self.repository.request_jobs, 'isolated-threshold', self.cog()._execute_requested_action, limit=5)
        self.assertEqual(self.repository.active_points(1, 2), 1)
        self.assertEqual(self.port.actions, ['ban'])

    async def test_point_retry_reuses_case_and_threshold_intent_after_restart(self):
        self.settings.set_module(1, 'infractions', enabled=True,
            settings={'point_thresholds': [{'points': 1, 'action': {'type': 'ban'}}]})
        await self.service.warn(self.guild, self.member, 'warning', 3, notify=False, execution_key='interaction:1')
        restarted = ModerationService(self.port, ModerationRepository(self.url), self.settings)
        await restarted.warn(self.guild, self.member, 'warning', 3, notify=False, execution_key='interaction:1')
        self.assertEqual(self.repository.active_points(1, 2), 1)
        self.assertEqual(len(self.repository.recent_cases(1, 2)), 1)
        self.repository.purge_moderation_evidence(now=10**12)
        await run_batch(self.repository.request_jobs, 'threshold-restart', self.cog()._execute_requested_action, limit=5)
        self.assertEqual(self.port.actions, ['ban'])
        with self.repository._connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM moderation_action_requests').fetchone()['n'], 1)
            request = c.execute('SELECT * FROM moderation_action_requests').fetchone()
        # ACK/database-finish loss replay must reuse the sanction receipt.
        result = await restarted.execute_threshold(self.guild, dict(request))
        self.assertEqual(result['status'], 'success')
        self.assertEqual(self.port.actions, ['ban'])

    async def test_rule_point_case_failure_rolls_back_and_replay_is_idempotent(self):
        from moderation.contracts import ActionContext
        event = self.repository.create_moderation_event(1, family='automod', event_type='message_create',
            source='automod', reason='rule', target_user_id=2, dedupe_key='rule-event')
        rule = {'id': None, 'family': 'automod', 'mode': 'enforce', 'actions': [{'type': 'points', 'points': 2}]}
        with self.repository._connection() as c:
            c.execute("ALTER TABLE moderation_cases ADD CONSTRAINT isolated_rule_reject CHECK(reason <> 'reject-rule')")
        with self.assertRaises(Exception):
            await self.service.execute_actions(ActionContext(self.guild, self.member), rule, 'reject-rule', event, {})
        self.assertEqual(self.repository.active_points(1, 2), 0)
        result = await self.service.execute_actions(ActionContext(self.guild, self.member), rule, 'rule', event, {})
        replay = await self.service.execute_actions(ActionContext(self.guild, self.member), rule, 'rule', event, {})
        self.assertEqual(result, replay)
        self.assertEqual(self.repository.active_points(1, 2), 2)
        self.assertEqual(len(self.repository.recent_cases(1, 2)), 1)

    async def test_fake_threshold_flag_and_forged_parent_are_rejected(self):
        identifier = self.repository.enqueue_moderation_action(1, 0, 'threshold', target_user_id=2,
            options={'point_event_id': 123, 'internal': True}, dedupe_key='forged-threshold')
        await run_batch(self.repository.request_jobs, 'forged-threshold', self.cog()._execute_requested_action, limit=5)
        self.assertIsNone(self.repository.threshold_intent(identifier))
        self.assertEqual(self.port.actions, [])

    async def test_api_cannot_enqueue_internal_threshold_action(self):
        from api_support import ApiFixture
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        api = ApiFixture(Path(temp.name), self.addCleanup)
        self.addCleanup(api.client.close)
        GuildSettingsRepository(api.database).set_module(1, 'moderation', enabled=True)
        response = api.client.post('/api/v1/guilds/1/moderation/actions', headers=api.headers,
            json={'action': 'threshold', 'target_user_id': '2', 'confirmed': True,
                  'reason': 'fake internal', 'options': {'point_event_id': 1, 'internal': True}})
        self.assertEqual(response.status_code, 422, response.text)
        with ModerationRepository(api.database)._connection() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM moderation_action_requests').fetchone()['n'], 0)

    async def test_unlock_uses_authoritative_permissions_when_gateway_cache_lags(self):
        cached = {'send_messages': None, 'send_messages_in_threads': None}
        remote = dict(cached)
        changed, allow_ack = asyncio.Event(), asyncio.Event()
        channel = MagicMock(spec=discord.TextChannel)
        channel.id, channel.category_id = 10, None
        channel.guild = SimpleNamespace(id=1)
        channel.overwrites_for.side_effect = lambda role: discord.PermissionOverwrite(**cached)
        fresh = MagicMock(spec=discord.TextChannel)
        fresh.id, fresh.guild = 10, SimpleNamespace(id=1)
        fresh.overwrites_for.side_effect = lambda role: discord.PermissionOverwrite(**remote)

        async def set_permissions(role, *, overwrite, reason):
            remote.update(send_messages=overwrite.send_messages,
                          send_messages_in_threads=overwrite.send_messages_in_threads)
            changed.set()
            await allow_ack.wait()

        channel.set_permissions = fresh.set_permissions = AsyncMock(side_effect=set_permissions)
        role = SimpleNamespace(id=1)
        guild = SimpleNamespace(id=1, channels=[channel], default_role=role,
            me=SimpleNamespace(guild_permissions=SimpleNamespace(manage_channels=True)),
            get_channel=lambda identifier: channel, get_role=lambda identifier: role,
            fetch_channel=AsyncMock(return_value=fresh))
        adapter = DiscordModerationAdapter(SimpleNamespace(get_guild=lambda identifier: guild))
        service = ModerationService(adapter, self.repository, self.settings)
        task = asyncio.create_task(service.lockdown(self.guild, 'raid', 1))
        await asyncio.wait_for(changed.wait(), 5)
        allow_ack.set()
        lockdown = await task
        result = await service.unlock_lockdown(self.guild, lockdown)
        self.assertEqual(result, {'restored': 1, 'conflicts': 0})
        self.assertIsNone(self.repository.active_lockdown(1))
        self.assertEqual(remote, cached, 'DB completion must imply the remote overwrite was restored')

    async def test_failed_fresh_read_and_human_conflict_keep_lockdown_active(self):
        from test_moderation_adapter import FakePort
        port = FakePort()
        service = ModerationService(port, self.repository, self.settings)
        await service.lockdown(self.guild, 'raid', 1)
        with patch.object(port, 'fresh_overwrite', new=AsyncMock(side_effect=ActionFailure('fresh read denied'))):
            with self.assertRaises(ActionFailure):
                await service.unlock_lockdown(self.guild)
        active = self.repository.active_lockdown(1)
        self.assertIn('fresh read denied', active['last_error'])
        port.permissions = {'send_messages': True, 'send_messages_in_threads': None}
        result = await service.unlock_lockdown(self.guild)
        self.assertEqual(result['conflicts'], 1)
        self.assertIsNotNone(self.repository.active_lockdown(1))
        self.assertTrue(port.permissions['send_messages'])

    async def test_ban_audit_and_current_reason_must_both_match_execution(self):
        current = SimpleNamespace(reason='reason [Tueka execution:5]')
        entries = [SimpleNamespace(target=SimpleNamespace(id=2), user=SimpleNamespace(id=9), reason=current.reason)]
        async def audit_logs(**kwargs):
            for entry in entries:
                yield entry
        guild = SimpleNamespace(audit_logs=audit_logs, fetch_ban=AsyncMock(return_value=current))
        adapter = DiscordModerationAdapter(SimpleNamespace(get_guild=lambda identifier: guild, user=SimpleNamespace(id=9)))
        self.assertTrue(await adapter.applied(1, 2, 'tempban', 100, 5, 1))
        current.reason = 'new human decision'
        self.assertFalse(await adapter.applied(1, 2, 'tempban', 100, 5, 1))
        current.reason = 'reason [Tueka execution:5]'
        entries.insert(0, SimpleNamespace(target=SimpleNamespace(id=2), user=SimpleNamespace(id=8), reason=current.reason))
        self.assertFalse(await adapter.applied(1, 2, 'tempban', 100, 5, 1))

    async def test_pending_tempban_evidence_is_kept_past_normal_retention(self):
        case = await self.service.apply_case(self.guild, self.member, 'tempban', 'temporary',
            duration_minutes=525600, notify=False, execution_key='long-temp')
        self.repository.purge_moderation_evidence(now=10**12)
        receipt = self.repository.case_execution(1, 'case:long-temp')
        self.assertIn('tempban', receipt['evidence_json'])
        await self.expire(case)
        self.assertFalse(self.port.banned)


if __name__ == '__main__':
    unittest.main()
