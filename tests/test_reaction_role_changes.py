import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from db_support import prepare_database
from discord_io import DiscordFailure
from reaction_roles.repository import ReactionRoleRepository
from reaction_roles.roles import RoleChangeService
from reaction_roles.service import ReactionRoleService
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
        self.repo = ReactionRoleRepository(prepare_database(Path(self.temp.name) / 'roles.db'))
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
