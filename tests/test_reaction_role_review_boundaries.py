"""Reaction Role guild, cleanup, expiry, and editing safety boundaries."""
import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


from db_support import prepare_database
from jobs import Outcome, run_batch
from reaction_roles.repository import ReactionRoleRepository
from reaction_roles.service import ReactionRoleService
from reaction_roles.roles import RoleChangeService
from reaction_roles.delivery import ReactionRoleDeliveryService
from reaction_roles.models import ReactionRoleValidationError
from cogs.community.reaction_roles import ReactionRolesCog
from test_reaction_roles import message


class Port:
    def __init__(self):
        self.roles = set()
        self.cleaned = []

    async def member_role_ids(self, guild_id, user_id):
        return set(self.roles)

    async def role(self, guild_id, user_id, role_id, *, add, reason):
        self.roles.add(role_id) if add else self.roles.discard(role_id)

    async def owns_role_change(self, operation, role_id):
        return True

    async def remove_selection(self, guild_id, channel_id, message_id, emoji, user_id):
        self.cleaned.append((guild_id, message_id, emoji, user_id))


class ReactionRoleReviewBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = ReactionRoleRepository(prepare_database(Path(self.temp.name) / 'rr', self.addCleanup))
        self.decisions = ReactionRoleService(self.repo)
        self.port = Port()
        self.roles = RoleChangeService(self.repo, self.port)

    def create(self, guild=1, **kwargs):
        config = self.decisions.create(guild, message(**kwargs))
        self.repo.set_discord_message(config['id'], 900 + config['id'])
        return self.repo.message(guild, config['id'])

    async def react(self, config, event='add', mapping=None):
        mapping = mapping or config['mappings'][0]
        decision = self.decisions.decide(config, mapping, event=event, user_id=30, member_role_ids=set(self.port.roles))
        if decision.allowed and decision.operation != 'none':
            await self.roles.apply(config, mapping, 30, decision)

    async def test_link_cleanup_does_not_revoke_same_role_selected_on_new_panel(self):
        first = self.create()
        second = self.create(channel_id=11)
        self.repo.create_link_group(1, 'Same role', [first['id'], second['id']])
        first, second = [self.repo.message(1, c['id']) for c in (first, second)]
        await self.react(first)
        await self.react(second)
        with self.repo.connection() as c:
            row = c.execute("SELECT * FROM reaction_role_outbox WHERE action='clear_selection'").fetchone()
        import json
        item = dict(row)
        item['payload'] = json.loads(item['payload_json'])
        await ReactionRoleDeliveryService(self.repo, self.port).outbox(item)
        # Discord emits raw_reaction_remove for the user's reaction removed by Bot.
        await self.react(first, 'remove')
        self.assertEqual(len(self.repo.assignments(30, config_id=second['id'])), 1)
        self.assertEqual(self.port.roles, {20}, 'Old-panel cleanup removed the current selected role')

    async def test_untracked_normal_role_can_still_be_removed(self):
        config = self.create()
        self.port.roles = {20}
        decision = self.decisions.decide(config, config['mappings'][0], event='remove', user_id=30, member_role_ids={20})
        self.assertEqual(decision.operation, 'remove')
        await self.react(config, 'remove')
        self.assertEqual(self.port.roles, set())

    async def test_linked_other_role_does_not_block_normal_removal(self):
        first = self.create()
        second = self.create(channel_id=11, role_id=21)
        self.repo.create_link_group(1, 'Different roles', [first['id'], second['id']])
        first, second = [self.repo.message(1, c['id']) for c in (first, second)]
        await self.react(second)
        self.port.roles.add(20)
        await self.react(first, 'remove')
        self.assertEqual(self.port.roles, {21})
        self.assertEqual(len(self.repo.assignments(30, config_id=second['id'])), 1)

    async def test_current_selection_of_shared_link_role_can_be_removed(self):
        first = self.create()
        second = self.create(channel_id=11)
        self.repo.create_link_group(1, 'Same role', [first['id'], second['id']])
        first, second = [self.repo.message(1, c['id']) for c in (first, second)]
        await self.react(first)
        await self.react(second)
        await self.react(second, 'remove')
        self.assertEqual(self.port.roles, set())
        self.assertEqual(self.repo.assignments(30, config_id=second['id']), [])

    async def test_lease_recheck_preserves_link_selection_created_after_remove_decision(self):
        first = self.create()
        second = self.create(channel_id=11)
        self.repo.create_link_group(1, 'Same role', [first['id'], second['id']])
        first, second = [self.repo.message(1, c['id']) for c in (first, second)]
        mapping = first['mappings'][0]
        stale = self.decisions.decide(first, mapping, event='remove', user_id=30, member_role_ids={20})
        self.assertEqual(stale.operation, 'remove')
        await self.react(second)
        await self.roles.apply(first, mapping, 30, stale)
        self.assertEqual(self.port.roles, {20})

    async def test_mapping_edit_does_not_erase_temporary_role_expiry(self):
        config = self.create(behavior='temp')
        await self.react(config)
        with self.repo.connection() as c:
            job = dict(c.execute("SELECT * FROM reaction_role_schedules WHERE kind='temp_role'").fetchone())
        edited = {**config, 'mappings': [{'emoji': '😀', 'role_id': 21}]}
        self.decisions.update(1, config['id'], edited, config['revision'])
        await ReactionRoleDeliveryService(self.repo, self.port).schedule(job)
        self.assertEqual(self.port.roles, set(), 'Mapping replacement cascaded away assignment and expiry silently skipped old role')

    async def test_detached_expiry_preserves_another_current_selection_of_same_role(self):
        config = self.create(behavior='temp')
        await self.react(config)
        with self.repo.connection() as c:
            job = dict(c.execute("SELECT * FROM reaction_role_schedules WHERE kind='temp_role'").fetchone())
        self.decisions.update(1, config['id'], {**config, 'mappings': [{'emoji': '😀', 'role_id': 21}]}, config['revision'])
        other = self.create(channel_id=11)
        await self.react(other)
        await ReactionRoleDeliveryService(self.repo, self.port).schedule(job)
        self.assertEqual(self.port.roles, {20})

    async def test_only_latest_temporary_expiry_survives_mapping_edit(self):
        config = self.create(behavior='temp')
        await self.react(config)
        with self.repo.connection() as c:
            old_job = dict(c.execute("SELECT * FROM reaction_role_schedules WHERE kind='temp_role'").fetchone())
        mapping = config['mappings'][0]
        latest_due = old_job['due_at'] + 60
        self.repo.activate_assignment(1, config['id'], mapping['id'], 30, 20, latest_due)
        with self.repo.connection() as c:
            latest_job = dict(c.execute("SELECT * FROM reaction_role_schedules WHERE due_at=%s", (latest_due,)).fetchone())
        self.decisions.update(1, config['id'], {**config, 'mappings': [{'emoji': '😀', 'role_id': 21}]}, config['revision'])
        delivery = ReactionRoleDeliveryService(self.repo, self.port)
        await delivery.schedule(old_job)
        self.assertEqual(self.port.roles, {20})
        await delivery.schedule(latest_job)
        self.assertEqual(self.port.roles, set())

    async def test_current_self_destruct_atomically_queues_delete_and_removes_config(self):
        config = self.create()
        due = int(time.time()) - 1
        config = self.decisions.update(1, config['id'], {**config, 'self_destruct_at': due}, config['revision'])
        claim = self.repo.schedule_jobs.claim('isolated-review')
        await ReactionRoleDeliveryService(self.repo, self.port).schedule(claim.payload)
        self.assertIsNone(self.repo.message(1, config['id']))
        with self.repo.connection() as c:
            deleted = c.execute("SELECT payload_json FROM reaction_role_outbox WHERE action='delete'").fetchall()
        self.assertEqual(len(deleted), 1)

    async def test_claimed_self_destruct_cannot_delete_panel_after_cancellation(self):
        config = self.create()
        config = self.decisions.update(1, config['id'], {**config, 'self_destruct_at': int(time.time()) - 1}, config['revision'])
        claim = self.repo.schedule_jobs.claim('isolated-review')
        self.assertIsNotNone(claim)
        ready, release = asyncio.Event(), asyncio.Event()

        async def queued_worker():
            ready.set()
            await release.wait()
            return await ReactionRoleDeliveryService(self.repo, self.port).schedule(claim.payload)

        task = asyncio.create_task(queued_worker())
        await ready.wait()
        self.decisions.update(1, config['id'], {**config, 'self_destruct_at': None}, config['revision'])
        release.set()
        await task
        self.assertIsNotNone(self.repo.message(1, config['id']), 'Claimed stale schedule deleted panel after administrator cancelled self-destruct')

    async def test_foreign_link_group_cannot_deactivate_other_guild_assignment(self):
        first = self.create(guild=2)
        second = self.create(guild=2, channel_id=11, role_id=21)
        group = self.repo.create_link_group(2, 'Other guild', [first['id'], second['id']])
        first = self.repo.message(2, first['id'])
        await self.react(first)
        # This field is accepted by the public create/update schema and checked_reaction_role.
        raw = {**message(role_id=22), 'link_group_id': group['id']}
        with self.assertRaises(ReactionRoleValidationError):
            self.decisions.create(1, raw)
        self.assertEqual(len(self.repo.assignments(30, config_id=first['id'])), 1,
                         'Guild 1 attachment to Guild 2 group removed Guild 2 assignment')

    async def test_reset_binding_checks_config_guild_before_deleting_receipt(self):
        config = self.create(guild=2, behavior='binding')
        await self.react(config)
        cog = object.__new__(ReactionRolesCog)
        cog.repository = self.repo
        interaction = SimpleNamespace(guild_id=1, response=SimpleNamespace(send_message=AsyncMock()))
        with self.assertRaises(ReactionRoleValidationError):
            await ReactionRolesCog.reset_binding_command.callback(cog, interaction, config['id'], SimpleNamespace(id=30))
        self.assertIsNotNone(self.repo.binding_receipt(config['id'], 30), 'Guild 1 command erased Guild 2 binding history')

    async def test_whitelist_add_works_on_default_blacklist_panel(self):
        config = self.create()
        cog = object.__new__(ReactionRolesCog)
        cog.repository, cog.service = self.repo, self.decisions
        interaction = SimpleNamespace(guild_id=1, guild=SimpleNamespace(emojis=[]), user=SimpleNamespace(id=40),
                                      response=SimpleNamespace(send_message=AsyncMock()))
        await ReactionRolesCog._access(cog, interaction, config['id'], 'whitelist', 'add', SimpleNamespace(id=50))
        updated = self.repo.message(1, config['id'])
        self.assertEqual(updated['whitelist_role_ids'], [50], 'Whitelist command retained access_policy=blacklist and validation rejected it')

    async def test_whitelist_switch_preserves_existing_blacklist_on_conflict(self):
        config = self.create()
        config = self.decisions.update(1, config['id'], {**config, 'blacklist_role_ids': [51]}, config['revision'])
        cog = object.__new__(ReactionRolesCog)
        cog.repository, cog.service = self.repo, self.decisions
        interaction = SimpleNamespace(guild_id=1, guild=SimpleNamespace(emojis=[]), user=SimpleNamespace(id=40),
                                      response=SimpleNamespace(send_message=AsyncMock()))
        await ReactionRolesCog._access(cog, interaction, config['id'], 'whitelist', 'add', SimpleNamespace(id=50))
        updated = self.repo.message(1, config['id'])
        self.assertEqual(updated['blacklist_role_ids'], [51])
        self.assertEqual(updated['whitelist_role_ids'], [])
        self.assertEqual(updated['revision'], config['revision'])

    async def test_foreign_group_update_rejected_without_replacing_local_mapping(self):
        first, second = self.create(guild=2), self.create(guild=2, channel_id=11, role_id=21)
        group = self.repo.create_link_group(2, 'Other guild', [first['id'], second['id']])
        local = self.create()
        with self.assertRaises(ReactionRoleValidationError):
            self.decisions.update(1, local['id'], {**local, 'link_group_id': group['id']}, local['revision'])
        self.assertEqual(self.repo.message(1, local['id']), local)


class ReactionRoleRetryReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_database_failure_does_not_cancel_self_destruct(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        repo = ReactionRoleRepository(prepare_database(Path(temp.name) / 'rr', self.addCleanup))
        service = ReactionRoleService(repo)
        config = service.create(1, {**message(), 'self_destruct_at': 100})
        repo.set_discord_message(config['id'], 999)
        delivery = ReactionRoleDeliveryService(repo, object())
        clock = [100]
        repo.schedule_jobs.clock = lambda: clock[0]
        original = repo.consume_self_destruct
        calls = []

        def transient_once(*args):
            calls.append(args)
            if len(calls) == 1:
                raise RuntimeError('Injected transient database failure before commit')
            return original(*args)

        with patch.object(repo, 'consume_self_destruct', side_effect=transient_once):
            await run_batch(repo.schedule_jobs, 'reviewer', delivery.schedule, limit=1)
            with repo.connection() as connection:
                retried = dict(connection.execute("SELECT * FROM reaction_role_schedules WHERE kind='self_destruct'").fetchone())
            self.assertEqual(retried['state'], 'retry')
            self.assertNotEqual(retried['due_at'], 100)
            clock[0] = retried['due_at']
            await run_batch(repo.schedule_jobs, 'reviewer', delivery.schedule, limit=1)
        with repo.connection() as connection:
            final = dict(connection.execute("SELECT * FROM reaction_role_schedules WHERE kind='self_destruct'").fetchone())
            deletes = connection.execute("SELECT id FROM reaction_role_outbox WHERE action='delete'").fetchall()
        print({'calls': calls, 'retry_due': retried['due_at'], 'job_state': final['state'], 'config_remaining': repo.message(1, config['id']) is not None, 'delete_count': len(deletes)})
        self.assertIsNone(repo.message(1, config['id']), 'Retry backoff must not invalidate the unchanged self_destruct_at')
        self.assertEqual(len(deletes), 1)


    async def _temporary_retry(self, replace_mapping):
        from discord_io import DiscordFailure
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        repo = ReactionRoleRepository(prepare_database(Path(temp.name) / 'rr', self.addCleanup))
        service = ReactionRoleService(repo)
        config = service.create(1, message(behavior='temp'))
        mapping = config['mappings'][0]
        repo.activate_assignment(1, config['id'], mapping['id'], 30, 20, 100)

        class Port:
            roles = {20}
            calls = 0
            async def role(self, guild_id, user_id, role_id, *, add, reason):
                self.calls += 1
                if self.calls == 1:
                    raise DiscordFailure('Injected HTTP 429 before role removal', retry=True)
                self.roles.discard(role_id)

        port = Port()
        delivery = ReactionRoleDeliveryService(repo, port)
        clock = [100]
        repo.schedule_jobs.clock = lambda: clock[0]
        await run_batch(repo.schedule_jobs, 'reviewer', delivery.schedule, limit=1)
        with repo.connection() as connection:
            retried = dict(connection.execute("SELECT * FROM reaction_role_schedules WHERE kind='temp_role'").fetchone())
        self.assertEqual(retried['state'], 'retry')
        if replace_mapping:
            service.update(1, config['id'], {**config, 'mappings': [{'emoji': '😀', 'role_id': 21}]}, config['revision'])
        clock[0] = retried['due_at']
        await run_batch(repo.schedule_jobs, 'reviewer', delivery.schedule, limit=1)
        with repo.connection() as connection:
            final = dict(connection.execute("SELECT * FROM reaction_role_schedules WHERE kind='temp_role'").fetchone())
        print({'replace_mapping': replace_mapping, 'retry_due': retried['due_at'], 'final_state': final['state'], 'mapping_id': final['mapping_id'], 'detached_role': final.get('role_id'), 'role_calls': port.calls, 'roles': sorted(port.roles)})
        self.assertEqual(port.roles, set(), 'Retry must remove the expired role despite queue backoff')

    async def test_temporary_expiry_retry_preserves_original_expiration(self):
        await self._temporary_retry(False)

    async def test_mapping_edit_preserves_temporary_expiry_already_in_retry(self):
        await self._temporary_retry(True)

    async def test_older_detached_schedule_preserves_newer_detached_expiry(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        repo = ReactionRoleRepository(prepare_database(Path(temp.name) / 'rr', self.addCleanup))
        service = ReactionRoleService(repo)
        config = service.create(1, message(behavior='temp'))
        repo.activate_assignment(1, config['id'], config['mappings'][0]['id'], 30, 20, 100)
        config = service.update(1, config['id'], {**config, 'mappings': [{'emoji': '🎮', 'role_id': 20}]}, config['revision'])
        repo.activate_assignment(1, config['id'], config['mappings'][0]['id'], 30, 20, 200)
        config = service.update(1, config['id'], {**config, 'mappings': [{'emoji': '🎨', 'role_id': 20}]}, config['revision'])

        class Port:
            roles = {20}
            async def role(self, guild_id, user_id, role_id, *, add, reason):
                self.roles.discard(role_id)

        port = Port()
        delivery = ReactionRoleDeliveryService(repo, port)
        repo.schedule_jobs.clock = lambda: 100
        await run_batch(repo.schedule_jobs, 'reviewer', delivery.schedule, limit=1)
        with repo.connection() as connection:
            jobs = [dict(row) for row in connection.execute("SELECT due_at,mapping_id,role_id,state FROM reaction_role_schedules ORDER BY due_at").fetchall()]
        print({'detached_jobs': jobs, 'roles_after_old_deadline': sorted(port.roles)})
        self.assertEqual(port.roles, {20}, 'An older detached expiry must not revoke a newer detached selection')

    async def test_shorter_new_selection_supersedes_older_detached_deadline(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        repo = ReactionRoleRepository(prepare_database(Path(temp.name) / 'rr', self.addCleanup))
        service = ReactionRoleService(repo)
        config = service.create(1, message(behavior='temp'))
        repo.activate_assignment(1, config['id'], config['mappings'][0]['id'], 30, 20, 200)
        config = service.update(1, config['id'], {**config, 'mappings': [{'emoji': '🎮', 'role_id': 20}]}, config['revision'])
        repo.activate_assignment(1, config['id'], config['mappings'][0]['id'], 30, 20, 100)
        service.update(1, config['id'], {**config, 'mappings': [{'emoji': '🎨', 'role_id': 20}]}, config['revision'])
        port = Port()
        port.roles = {20}
        delivery = ReactionRoleDeliveryService(repo, port)
        repo.schedule_jobs.clock = lambda: 100
        await run_batch(repo.schedule_jobs, 'reviewer', delivery.schedule, limit=10)
        self.assertEqual(port.roles, set(), 'Newest selection uses its own shorter duration')
        port.roles = {20}
        repo.schedule_jobs.clock = lambda: 200
        await run_batch(repo.schedule_jobs, 'reviewer', delivery.schedule, limit=10)
        self.assertEqual(port.roles, {20}, 'Superseded old deadline must never reactivate')

    async def test_superseded_claim_reloads_terminal_state_before_role_mutation(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        repo = ReactionRoleRepository(prepare_database(Path(temp.name) / 'rr', self.addCleanup))
        service = ReactionRoleService(repo)
        config = service.create(1, message(behavior='temp'))
        repo.activate_assignment(1, config['id'], config['mappings'][0]['id'], 30, 20, 100)
        config = service.update(1, config['id'], {**config, 'mappings': [{'emoji': '🎮', 'role_id': 20}]}, config['revision'])
        repo.schedule_jobs.clock = lambda: 100
        stale = repo.schedule_jobs.claim('reviewer')
        repo.activate_assignment(1, config['id'], config['mappings'][0]['id'], 30, 20, 200)
        service.update(1, config['id'], {**config, 'mappings': [{'emoji': '🎨', 'role_id': 20}]}, config['revision'])
        port = Port()
        port.roles = {20}
        await ReactionRoleDeliveryService(repo, port).schedule(stale.payload)
        self.assertEqual(port.roles, {20})

    async def test_selection_generation_does_not_supersede_another_guild_deadline(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        repo = ReactionRoleRepository(prepare_database(Path(temp.name) / 'rr', self.addCleanup))
        service = ReactionRoleService(repo)
        for guild, due in ((2, 100), (1, 200)):
            config = service.create(guild, message(behavior='temp'))
            repo.activate_assignment(guild, config['id'], config['mappings'][0]['id'], 30, 20, due)
            service.update(guild, config['id'], {**config, 'mappings': [{'emoji': '🎮', 'role_id': 20}]}, config['revision'])
        port = Port()
        port.roles = {20}
        repo.schedule_jobs.clock = lambda: 100
        await run_batch(repo.schedule_jobs, 'reviewer', ReactionRoleDeliveryService(repo, port).schedule, limit=10)
        self.assertEqual(port.roles, set())
        with repo.connection() as c:
            latest = c.execute('SELECT state FROM reaction_role_schedules WHERE guild_id=1').fetchone()
        self.assertEqual(latest['state'], 'pending')

    async def test_retry_timestamp_can_equal_a_superseded_original_deadline(self):
        from discord_io import DiscordFailure
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        repo = ReactionRoleRepository(prepare_database(Path(temp.name) / 'rr', self.addCleanup))
        config = ReactionRoleService(repo).create(1, message(behavior='temp'))
        mapping = config['mappings'][0]
        repo.activate_assignment(1, config['id'], mapping['id'], 30, 20, 150)
        repo.activate_assignment(1, config['id'], mapping['id'], 30, 20, 120)

        class RetryPort(Port):
            calls = 0
            async def role(self, guild_id, user_id, role_id, *, add, reason):
                self.calls += 1
                if self.calls == 1:
                    raise DiscordFailure('Injected HTTP 429', retry=True)
                await super().role(guild_id, user_id, role_id, add=add, reason=reason)

        port = RetryPort()
        port.roles = {20}
        delivery = ReactionRoleDeliveryService(repo, port)
        repo.schedule_jobs.clock = lambda: 120
        await run_batch(repo.schedule_jobs, 'reviewer', delivery.schedule, limit=1)
        with repo.connection() as c:
            retry = c.execute("SELECT scheduled_for,due_at,state FROM reaction_role_schedules WHERE state='retry'").fetchone()
        self.assertEqual(retry, {'scheduled_for': 120, 'due_at': 150, 'state': 'retry'})
        repo.schedule_jobs.clock = lambda: 150
        # Both the superseded assignment cleanup and the current retry are due.
        await run_batch(repo.schedule_jobs, 'reviewer', delivery.schedule, limit=10)
        self.assertEqual(port.roles, set())

    async def test_superseded_temp_assignment_does_not_block_current_detached_expiry(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        repo = ReactionRoleRepository(prepare_database(Path(temp.name) / 'rr', self.addCleanup))
        service = ReactionRoleService(repo)
        older = service.create(1, message(behavior='temp'))
        newer = service.create(1, message(behavior='temp', channel_id=11))
        repo.activate_assignment(1, older['id'], older['mappings'][0]['id'], 30, 20, 100)
        repo.activate_assignment(1, newer['id'], newer['mappings'][0]['id'], 30, 20, 200)
        service.update(1, newer['id'], {**newer, 'mappings': [{'emoji': '🎮', 'role_id': 20}]}, newer['revision'])
        port = Port()
        port.roles = {20}
        repo.schedule_jobs.clock = lambda: 200
        await run_batch(repo.schedule_jobs, 'reviewer', ReactionRoleDeliveryService(repo, port).schedule, limit=10)
        self.assertEqual(port.roles, set())



class ReactionRoleFollowupTests(unittest.IsolatedAsyncioTestCase):
    setUp = ReactionRoleReviewBoundaryTests.setUp
    create = ReactionRoleReviewBoundaryTests.create
    react = ReactionRoleReviewBoundaryTests.react

    async def test_cleanup_generation_distinguishes_reselection_in_same_second(self):
        first, second = self.create(), self.create(channel_id=11)
        self.repo.create_link_group(1, 'Same-second cycle', [first['id'],second['id']])
        first, second = [self.repo.message(1,c['id']) for c in (first,second)]
        with patch('reaction_roles.repository.time.time', return_value=1000):
            await self.react(first)
            old = self.repo.assignments(30, config_id=first['id'])[0]
            await self.react(second)
            with self.repo.connection() as c:
                stale = dict(c.execute("SELECT * FROM reaction_role_outbox WHERE action='clear_selection' ORDER BY id LIMIT 1").fetchone())
            await self.react(first)
            current = self.repo.assignments(30, config_id=first['id'])[0]
        self.assertEqual(old['updated_at'], current['updated_at'])
        self.assertNotEqual(old['generation'], current['generation'])
        stale['payload'] = json.loads(stale['payload_json'])
        await ReactionRoleDeliveryService(self.repo, self.port).outbox(stale)
        self.assertEqual(self.port.cleaned, [])
        self.assertEqual(self.port.roles, {20})

    async def test_result_save_rechecks_queue_token_after_discord_wait(self):
        for reclaimed in (False, True):
            with self.subTest(reclaimed=reclaimed):
                config = self.create(behavior='temp', channel_id=100 + int(reclaimed))
                mapping = config['mappings'][0]
                self.repo.activate_assignment(1, config['id'], mapping['id'], 30, 20, 100)
                started, release = asyncio.Event(), asyncio.Event()
                clock = [100]
                self.repo.schedule_jobs.clock = lambda: clock[0]
                claim = self.repo.schedule_jobs.claim('first', lease_seconds=3)

                class WaitingPort(Port):
                    async def role(inner, *args, **kwargs):
                        started.set()
                        await release.wait()
                        await super().role(*args, **kwargs)

                port = WaitingPort()
                port.roles = {20}
                task = asyncio.create_task(ReactionRoleDeliveryService(self.repo, port).schedule(claim.payload))
                await started.wait()
                if reclaimed:
                    clock[0] = 104
                    successor = self.repo.schedule_jobs.claim('second', lease_seconds=3)
                    self.assertEqual(successor.id, claim.id)
                release.set()
                outcome = await task
                if reclaimed:
                    self.assertTrue(self.repo.assignments(30, config_id=config['id']), 'Expired owner cannot confirm the external result')
                    self.assertFalse(self.repo.schedule_jobs.finish(claim, outcome))
                    # The successor can reconcile by repeating the idempotent removal.
                    await ReactionRoleDeliveryService(self.repo, Port()).schedule(successor.payload)
                    self.repo.schedule_jobs.finish(successor, Outcome())
                else:
                    self.assertEqual(self.repo.assignments(30, config_id=config['id']), [])
                    self.assertTrue(self.repo.schedule_jobs.finish(claim, outcome))
    async def test_cycle_reselection_fences_old_clear_selection(self):
        first, second = self.create(), self.create(channel_id=11)
        self.repo.create_link_group(1, 'Cycle', [first['id'], second['id']])
        first, second = [self.repo.message(1, c['id']) for c in (first, second)]
        await self.react(first)
        await self.react(second)
        with self.repo.connection() as c:
            stale = dict(c.execute("SELECT * FROM reaction_role_outbox WHERE action='clear_selection' ORDER BY id LIMIT 1").fetchone())
        # User manually removes their still-visible A reaction, then re-adds it.
        await self.react(first, 'remove')
        await self.react(first)
        stale['payload'] = json.loads(stale['payload_json'])
        cleaned_before = len(self.port.cleaned)
        await ReactionRoleDeliveryService(self.repo, self.port).outbox(stale)
        # Fake gateway event emitted when remove_selection deletes user's reaction.
        if len(self.port.cleaned) > cleaned_before:
            await self.react(first, 'remove')
        print('cycle_cleanup', {'cleaned': self.port.cleaned, 'roles': sorted(self.port.roles),
                               'current_assignments': self.repo.assignments(30, config_id=first['id'])})
        self.assertEqual(self.port.roles, {20}, 'Old cleanup must not delete a newer selection of its target panel')

    async def test_expired_queue_token_cannot_mutate_role_after_reclaim(self):
        config = self.create(behavior='temp')
        mapping = config['mappings'][0]
        self.repo.activate_assignment(1, config['id'], mapping['id'], 30, 20, 100)
        self.port.roles = {20}
        clock = [100]
        self.repo.schedule_jobs.clock = lambda: clock[0]
        stale = self.repo.schedule_jobs.claim('first', lease_seconds=3)
        clock[0] = 104
        successor = self.repo.schedule_jobs.claim('second', lease_seconds=3)
        self.assertNotEqual(stale.token, successor.token)
        # A handler delayed before entering its member lease must recheck Queue ownership.
        result = await ReactionRoleDeliveryService(self.repo, self.port).schedule(stale.payload)
        stale_finished = self.repo.schedule_jobs.finish(stale, result)
        with self.repo.connection() as c:
            state = dict(c.execute('SELECT state,lease_owner FROM reaction_role_schedules WHERE id=%s', (stale.id,)).fetchone())
        print('stale_token', {'stale_finish_accepted': stale_finished, 'roles': sorted(self.port.roles), 'job': state})
        self.assertFalse(stale_finished)
        self.assertEqual(self.port.roles, {20}, 'An expired Queue token must not perform Discord effects')

    async def test_attached_expiry_preserves_new_permanent_selection(self):
        temporary = self.create(behavior='temp')
        mapping = temporary['mappings'][0]
        self.repo.activate_assignment(1, temporary['id'], mapping['id'], 30, 20, 100)
        self.port.roles = {20}
        permanent = self.create(channel_id=11)
        await self.react(permanent)
        self.repo.schedule_jobs.clock = lambda: 100
        claim = self.repo.schedule_jobs.claim('expiry')
        await ReactionRoleDeliveryService(self.repo, self.port).schedule(claim.payload)
        print('attached_shared_role', {'roles': sorted(self.port.roles),
                                      'permanent': self.repo.assignments(30, config_id=permanent['id'])})
        self.assertEqual(self.port.roles, {20}, 'Attached expiry must respect the same permanent ownership as detached expiry')

    async def test_panel_deletion_keeps_temporary_expiry_effective(self):
        temporary = self.create(behavior='temp')
        mapping = temporary['mappings'][0]
        self.repo.activate_assignment(1, temporary['id'], mapping['id'], 30, 20, 100)
        self.port.roles = {20}
        self.repo.delete_message(1, temporary['id'], recoverable=False, queue_delete=True)
        self.repo.schedule_jobs.clock = lambda: 100
        claim = self.repo.schedule_jobs.claim('expiry')
        await ReactionRoleDeliveryService(self.repo, self.port).schedule(claim.payload)
        print('deleted_panel_expiry', {'roles': sorted(self.port.roles), 'schedule_mapping': claim.payload['mapping_id']})
        self.assertEqual(self.port.roles, set(), 'Panel removal must retain the existing temporary role deadline')

    async def test_superseded_attached_assignment_does_not_consume_limit_forever(self):
        older = self.create(behavior='temp')
        older = self.decisions.update(1, older['id'], {
            **older, 'selection_limit': 1,
            'mappings': [{'emoji': '😀', 'role_id': 20}, {'emoji': '🎨', 'role_id': 21}],
        }, older['revision'])
        newer = self.create(behavior='temp', channel_id=11)
        self.repo.activate_assignment(1, older['id'], older['mappings'][0]['id'], 30, 20, 100)
        self.repo.activate_assignment(1, newer['id'], newer['mappings'][0]['id'], 30, 20, 200)
        self.port.roles = {20}
        self.repo.schedule_jobs.clock = lambda: 200
        claim = self.repo.schedule_jobs.claim('expiry')
        outcome = await ReactionRoleDeliveryService(self.repo, self.port).schedule(claim.payload)
        self.repo.schedule_jobs.finish(claim, outcome)
        decision = self.decisions.decide(older, older['mappings'][1], event='add', user_id=30,
                                         member_role_ids=set(self.port.roles))
        print('superseded_assignment_limit', {'roles': sorted(self.port.roles),
              'older_active': self.repo.assignments(30, config_id=older['id']),
              'allowed_new_role': decision.allowed, 'reason': decision.reason})
        self.assertTrue(decision.allowed, 'Expired superseded assignment must stop consuming panel selection capacity')



