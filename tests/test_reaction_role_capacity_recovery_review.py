"""Capacity and original-right preservation during durable role rollback.

Recovery may remain pending while capacity is occupied; it must neither exceed
max_members nor report rollback complete before restoring the original right.
Once the intervening holder releases the role, a later recovery must finish.
Unlike reconcile jobs (finite eight attempts), role-operation recovery remains
visible as pending/compensation_failed until compensation succeeds.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from db_support import prepare_database
from discord_io import DiscordFailure
from jobs import LostLease
from reaction_roles.repository import ReactionRoleRepository
from reaction_roles.roles import RoleChangeService
from reaction_roles.service import ReactionRoleService
from test_reaction_roles import message


class MemberRolePort:
    def __init__(self):
        self.roles = {30: set(), 31: set()}
        self.selected = {30, 31}
        self.fail_rollback = False
        self.audit = {}

    async def member_role_ids(self, guild_id, user_id):
        return set(self.roles[user_id])

    async def role_member_count(self, guild_id, role_id):
        return sum(role_id in roles for roles in self.roles.values())

    async def selection_present(self, guild_id, channel_id, message_id, emoji, user_id):
        return user_id in self.selected

    async def role(self, guild_id, user_id, role_id, *, add, reason):
        if self.fail_rollback and reason.startswith('Tueka role rollback:'):
            raise DiscordFailure('Injected temporary rollback outage', retry=True)
        if add:
            self.roles[user_id].add(role_id)
        else:
            self.roles[user_id].discard(role_id)
        self.audit[user_id, role_id] = reason

    async def owns_role_change(self, operation, role_id):
        return self.audit.get((operation['user_id'], role_id)) in {
            f'Tueka role operation:{operation["id"]}',
            f'Tueka role rollback:{operation["id"]}',
        }


class ReactionRoleCapacityRecoveryReviewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = ReactionRoleRepository(prepare_database(Path(temp.name) / 'rr', self.addCleanup))
        self.service = ReactionRoleService(self.repo)
        self.port = MemberRolePort()
        self.roles = RoleChangeService(self.repo, self.port)
        raw = message()
        raw['mappings'][0]['max_members'] = 1
        created = self.service.create(1, raw)
        self.repo.set_discord_message(created['id'], 900)
        self.config = self.repo.message(1, created['id'])
        self.mapping = self.config['mappings'][0]

    async def react(self, user_id, event):
        if event == 'add':
            self.port.selected.add(user_id)
        else:
            self.port.selected.discard(user_id)
        decision = self.service.decide(self.config, self.mapping, event=event,
            user_id=user_id, member_role_ids=set(self.port.roles[user_id]))
        return await self.roles.apply(self.config, self.mapping, user_id, decision, event=event)

    async def test_durable_rollback_preserves_capacity_then_restores_original_right(self):
        await self.react(30, 'add')
        original_generation = self.repo.assignments(30, config_id=self.config['id'])[0]['generation']
        self.port.fail_rollback = True
        # Fail at the actual transaction boundary, after the external remove.
        # begin_role_change and fail_role_compensation remain real repository calls.
        with patch.object(self.repo, 'commit_role_change', side_effect=RuntimeError('Injected DB commit outage')):
            with self.assertRaises(DiscordFailure):
                await self.react(30, 'remove')
        pending = self.repo.pending_role_changes(1)
        self.assertEqual(len(pending), 1)
        operation = pending[0]
        self.assertEqual(operation['result'], 'compensation_failed')
        self.assertEqual(operation['detail']['operation'], 'remove')
        self.assertEqual(self.port.roles[30], set())
        self.assertEqual(self.repo.assignments(30, config_id=self.config['id'])[0]['generation'], original_generation)

        # Another member can acquire the externally vacant capacity in the current
        # ordinary apply path. The persisted A operation was not fabricated.
        await self.react(31, 'add')
        self.assertEqual(self.port.roles[31], {20})
        self.port.fail_rollback = False
        try:
            await self.roles.recover(operation)
        except (DiscordFailure, LostLease):
            pass  # Deferral is valid; abandoning A's original right is not.
        self.assertLessEqual(await self.port.role_member_count(1, 20), 1,
            'Durable rollback restored A over B without honoring max_members=1')
        self.assertFalse(self.repo.role_change_finished(operation['id']),
            'Occupied capacity must leave A compensation visible for later recovery')
        self.assertEqual(len(self.repo.pending_role_changes(1)), 1)

        await self.react(31, 'remove')
        await self.roles.recover(operation)
        self.assertEqual(self.port.roles, {30: {20}, 31: set()})
        self.assertTrue(self.repo.role_change_finished(operation['id']))
        self.assertEqual(self.repo.pending_role_changes(1), [])
        self.assertEqual(self.repo.assignments(30, config_id=self.config['id'])[0]['generation'], original_generation)

    async def test_immediate_rollback_reuses_held_target_capacity(self):
        await self.react(30, 'add')
        with patch.object(self.repo, 'commit_role_change', side_effect=RuntimeError('Injected DB outage')):
            with self.assertRaisesRegex(RuntimeError, 'Injected DB outage'):
                await self.react(30, 'remove')
        self.assertEqual(self.port.roles[30], {20})
        self.assertEqual(self.repo.pending_role_changes(1), [])

    async def test_unique_rollback_restores_other_role_under_its_capacity(self):
        raw = message(behavior='unique')
        raw['mappings'][0]['max_members'] = 1
        raw['mappings'].append({'emoji': '✅', 'role_id': 21, 'max_members': 1})
        created = self.service.create(1, raw)
        self.repo.set_discord_message(created['id'], 901)
        config = self.repo.message(1, created['id'])
        first, second = config['mappings']
        decision = self.service.decide(config, first, event='add', user_id=30, member_role_ids=set())
        await self.roles.apply(config, first, 30, decision, event='add')
        original_generation = self.repo.assignments(30, config_id=config['id'])[0]['generation']
        decision = self.service.decide(config, second, event='add', user_id=30, member_role_ids={20})
        with patch.object(self.repo, 'commit_role_change', side_effect=RuntimeError('Injected unique DB outage')):
            with self.assertRaisesRegex(RuntimeError, 'Injected unique DB outage'):
                await self.roles.apply(config, second, 30, decision, event='add')
        self.assertEqual(self.port.roles[30], {20})
        self.assertEqual(self.repo.pending_role_changes(1), [])
        active = self.repo.assignments(30, config_id=config['id'])
        self.assertEqual([(row['role_id'], row['generation']) for row in active], [(20, original_generation)])
