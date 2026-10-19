import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from db_support import prepare_database
from discord_io import DiscordFailure
from reaction_roles.repository import ReactionRoleRepository
from reaction_roles.roles import RoleChangeService
from reaction_roles.service import ReactionRoleService
from reaction_roles.discord_adapter import DiscordReactionRoleAdapter
from test_reaction_roles import message


class RolePort:
    def __init__(self):
        self.roles = {20}
        self.fail_restore = False
        self.owned = True

    async def owns_role_change(self, operation, role_id):
        return self.owned

    async def member_role_ids(self, guild_id, user_id):
        return set(self.roles)

    async def role(self, guild_id, user_id, role_id, *, add, reason):
        if self.fail_restore and 'rollback' in reason:
            raise DiscordFailure('permissions lost')
        self.roles.add(role_id) if add else self.roles.discard(role_id)


class RoleChangeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = ReactionRoleRepository(prepare_database(Path(self.temp.name) / 'roles.db', self.addCleanup))
        self.decisions = ReactionRoleService(self.repo)
        value = message(behavior='unique')
        value['mappings'].append({'emoji': '✅', 'role_id': 21, 'max_members': None})
        self.config = self.decisions.create(1, value)
        self.repo.set_discord_message(self.config['id'], 900)
        self.config = self.repo.message(1, self.config['id'])
        self.old, self.selected = self.config['mappings']
        self.repo.activate_assignment(1, self.config['id'], self.old['id'], 30, 20, None)
        self.port = RolePort()
        self.service = RoleChangeService(self.repo, self.port)
        self.decision = self.decisions.decide(self.config, self.selected, event='add', user_id=30, member_role_ids={20})

    async def test_database_failure_rolls_back_all_roles_without_partial_assignment_commit(self):
        with patch.object(self.repo, 'commit_role_change', side_effect=RuntimeError('database failed')):
            with self.assertRaises(RuntimeError):
                await self.service.apply(self.config, self.selected, 30, self.decision)
        self.assertEqual(self.port.roles, {20})
        self.assertEqual([row['role_id'] for row in self.repo.assignments(30, config_id=self.config['id'])], [20])
        self.assertEqual(self.repo.pending_role_changes(1), [])

    async def test_link_selection_removes_previous_message_role_and_commits_both_assignments(self):
        second = self.decisions.create(1, message(role_id=21))
        self.repo.create_link_group(1, 'Linked', [self.config['id'], second['id']])
        second = self.repo.message(1, second['id'])
        mapping = second['mappings'][0]
        decision = self.decisions.decide(second, mapping, event='add', user_id=30, member_role_ids={20})
        self.assertEqual(len(decision.conflicting_assignments), 1)
        await self.service.apply(second, mapping, 30, decision)
        self.assertEqual(self.port.roles, {21})
        self.assertEqual(self.repo.assignments(30, config_id=self.config['id']), [])
        self.assertEqual([row['role_id'] for row in self.repo.assignments(30, config_id=second['id'])], [21])

    async def test_concurrent_restore_consumes_snapshot_once(self):
        from concurrent.futures import ThreadPoolExecutor
        self.repo.delete_message(1, self.config['id'], recoverable=True)
        snapshot = self.repo.recovery(1, 900)
        def restore(identifier):
            value = self.decisions.validate({**snapshot, 'source': 'external', 'message_id': identifier,
                'self_destruct_at': None, 'link_group_id': None})
            try:
                self.repo.restore_message(1, 900, value, 30, expected_snapshot=snapshot)
                return 'created'
            except ValueError as error:
                return str(error)
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(restore, (901, 902)))
        self.assertCountEqual(results, ['created', 'recovery_not_found'])
        self.assertEqual(len(self.repo.messages(1)), 1)
        self.assertIsNone(self.repo.recovery(1, 900))

    async def test_restore_refuses_a_snapshot_changed_after_validation(self):
        self.repo.delete_message(1, self.config['id'], recoverable=True)
        snapshot = self.repo.recovery(1, 900)
        value = self.decisions.validate({**snapshot, 'source': 'external', 'message_id': 901})
        with self.assertRaisesRegex(RuntimeError, 'recovery_conflict'):
            self.repo.restore_message(1, 900, value, 30, expected_snapshot={**snapshot, 'name': 'Stale validation'})
        self.assertEqual(self.repo.messages(1), [])
        self.assertEqual(self.repo.recovery(1, 900), snapshot)

    async def test_all_seven_types_apply_add_and_remove_with_persisted_assignments(self):
        cases = {
            'normal': (set(), {20}, set()), 'unique': (set(), {20}, set()),
            'verify': (set(), {20}, {20}), 'binding': (set(), {20}, {20}),
            'drop': ({20}, set(), set()), 'reversed': ({20}, set(), {20}),
            'temp': (set(), {20}, set()),
        }
        for index,(behavior,(initial,after_add,after_remove)) in enumerate(cases.items()):
            with self.subTest(behavior=behavior):
                config=self.decisions.create(1,message(behavior=behavior,channel_id=100+index))
                self.repo.set_discord_message(config['id'],1000+index)
                config=self.repo.message(1,config['id']);mapping=config['mappings'][0]
                port=RolePort();port.roles=set(initial)
                service=RoleChangeService(self.repo,port)
                user=100+index
                for event,expected in [('add',after_add),('remove',after_remove)]:
                    decision=self.decisions.decide(config,mapping,event=event,user_id=user,member_role_ids=port.roles)
                    self.assertTrue(decision.allowed)
                    if decision.operation!='none':await service.apply(config,mapping,user,decision)
                    self.assertEqual(port.roles,expected)
                assigned={r['role_id'] for r in self.repo.assignments(user,config_id=config['id'])}
                self.assertEqual(assigned,after_remove)
                if behavior=='binding':
                    self.assertIsNotNone(self.repo.binding_receipt(config['id'],user))
                    self.assertFalse(self.decisions.decide(config,mapping,event='add',user_id=user,member_role_ids=port.roles).allowed)

    async def test_failed_compensation_survives_retention_and_can_resume_after_restart(self):
        self.port.fail_restore = True
        with patch.object(self.repo, 'commit_role_change', side_effect=RuntimeError('database failed')):
            with self.assertRaises(DiscordFailure) as failed:
                await self.service.apply(self.config, self.selected, 30, self.decision)
        self.assertTrue(failed.exception.partial)
        with patch('reaction_roles.repository.time.time', return_value=10 ** 12):
            self.repo.maintain()
        operation = self.repo.pending_role_changes(1)[0]
        self.port.fail_restore = False
        await RoleChangeService(self.repo, self.port).recover(operation)
        self.assertEqual(self.port.roles, {20})
        self.assertEqual(self.repo.pending_role_changes(1), [])

    async def test_success_commits_assignments_and_reaction_cleanup_together(self):
        await self.service.apply(self.config, self.selected, 30, self.decision)
        self.assertEqual(self.port.roles, {21})
        self.assertEqual([row['role_id'] for row in self.repo.assignments(30, config_id=self.config['id'])], [21])
        first = self.repo.outbox_jobs.claim('worker')
        second = self.repo.outbox_jobs.claim('worker')
        self.assertEqual(first.payload['action'], 'publish')
        self.assertEqual(second.payload['action'], 'clear_selection')
        self.assertEqual(second.payload['payload']['emoji'], self.old['emoji'])

    async def test_recovery_does_not_overwrite_unrelated_role_change(self):
        self.port.owned = False
        with patch.object(self.repo, 'commit_role_change', side_effect=RuntimeError('database failed')):
            with self.assertRaises(DiscordFailure):
                await self.service.apply(self.config, self.selected, 30, self.decision)
        self.assertEqual(self.port.roles, {21})
        self.assertEqual(len(self.repo.pending_role_changes(1)), 1)
        with self.assertRaises(DiscordFailure):
            await self.service.recover(self.repo.pending_role_changes(1)[0])
        self.assertEqual(self.port.roles, {21})


class RoleAdapterBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_changed_hierarchy_and_unmanageable_roles_never_call_discord_mutation(self):
        class Role:
            managed = False
            position = 5
            default = False
            def is_default(self): return self.default
            def __ge__(self, other): return self.position >= other
        for condition in ('hierarchy', 'managed', 'default', 'permission'):
            with self.subTest(condition=condition):
                role = Role()
                if condition == 'hierarchy': role.position = 10
                if condition == 'managed': role.managed = True
                if condition == 'default': role.default = True
                member = SimpleNamespace(add_roles=AsyncMock(), remove_roles=AsyncMock())
                guild = SimpleNamespace(get_member=lambda _: member, get_role=lambda _: role,
                    me=SimpleNamespace(top_role=10, guild_permissions=SimpleNamespace(manage_roles=condition != 'permission')))
                adapter = DiscordReactionRoleAdapter(SimpleNamespace(get_guild=lambda _: guild))
                for adding in (True, False):
                    with self.assertRaises(DiscordFailure):
                        await adapter.role(1, 30, 20, add=adding, reason='Isolated permission test')
                member.add_roles.assert_not_awaited()
                member.remove_roles.assert_not_awaited()

    async def test_missing_role_refuses_add_but_confirms_removal_without_mutation(self):
        member = SimpleNamespace(add_roles=AsyncMock(), remove_roles=AsyncMock())
        guild = SimpleNamespace(get_member=lambda _: member, get_role=lambda _: None)
        adapter = DiscordReactionRoleAdapter(SimpleNamespace(get_guild=lambda _: guild))
        with self.assertRaises(DiscordFailure):
            await adapter.role(1, 30, 20, add=True, reason='Isolated missing role test')
        await adapter.role(1, 30, 20, add=False, reason='Isolated missing role test')
        member.add_roles.assert_not_awaited()
        member.remove_roles.assert_not_awaited()
