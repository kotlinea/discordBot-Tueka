"""Reaction Role member ownership and delayed Gateway removal regressions."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from db_support import prepare_database
from reaction_roles.repository import ReactionRoleRepository
from reaction_roles.service import ReactionRoleService
from reaction_roles.roles import RoleChangeService
from reaction_roles.delivery import ReactionRoleDeliveryService
from test_reaction_roles import message
from test_reaction_role_review_boundaries import Port

class ReactionRoleFinalReviewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = ReactionRoleRepository(prepare_database(Path(temp.name) / 'rr', self.addCleanup))
        self.service = ReactionRoleService(self.repo)
        self.port = Port()
        self.port.selection_present = self.selection_present
        self.selected = set()
        self.roles = RoleChangeService(self.repo, self.port)

    async def selection_present(self, guild_id, channel_id, message_id, emoji, user_id):
        return message_id in self.selected

    def create(self, **kwargs):
        c = self.service.create(1, message(**kwargs))
        self.repo.set_discord_message(c['id'], 900 + c['id'])
        return self.repo.message(1, c['id'])

    async def react(self, c, event='add'):
        if event == 'add':
            self.selected.add(c['message_id'])
        d = self.service.decide(c, c['mappings'][0], event=event, user_id=30, member_role_ids=set(self.port.roles))
        if d.allowed and d.operation != 'none':
            await self.roles.apply(c, c['mappings'][0], 30, d, event=event)

    async def test_gateway_cleanup_remove_delayed_past_reselection(self):
        a, b = self.create(), self.create(channel_id=11)
        self.repo.create_link_group(1, 'same', [a['id'], b['id']])
        a, b = [self.repo.message(1, c['id']) for c in (a, b)]
        await self.react(a)
        await self.react(b)
        with self.repo.connection() as c:
            item = dict(c.execute("SELECT * FROM reaction_role_outbox WHERE action='clear_selection' ORDER BY id LIMIT 1").fetchone())
        item['payload'] = json.loads(item['payload_json'])
        cleaned, deliver_gateway = asyncio.Event(), asyncio.Event()
        original = self.port.remove_selection
        async def remove(*args):
            await original(*args)
            self.selected.discard(args[2])
            cleaned.set()  # REST succeeded, gateway notification not delivered yet.
        self.port.remove_selection = remove
        async def delayed_gateway():
            await cleaned.wait()
            await deliver_gateway.wait()
            await self.react(a, 'remove')
        gateway = asyncio.create_task(delayed_gateway())
        await ReactionRoleDeliveryService(self.repo, self.port).outbox(item)
        await cleaned.wait()
        await self.react(a)  # User re-adds A after REST cleanup but before old remove callback.
        generation = self.repo.assignments(30, config_id=a['id'])[0]['generation']
        deliver_gateway.set()
        await gateway
        print('delayed_cleanup', {'new_generation': generation, 'roles': sorted(self.port.roles), 'active': self.repo.assignments(30, config_id=a['id'])})
        self.assertEqual(self.port.roles, {20}, 'Old cleanup notification revoked a later A selection')

    async def test_decisions_precomputed_before_member_lease(self):
        a, b = self.create(), self.create(channel_id=11, role_id=21)
        self.repo.create_link_group(1, 'different', [a['id'], b['id']])
        a, b = [self.repo.message(1, c['id']) for c in (a, b)]
        da, db = [self.service.decide(c, c['mappings'][0], event='add', user_id=30, member_role_ids=set()) for c in (a, b)]
        # Two owners both decide before either member lease. Apply serially is the
        # exact lease ordering; no overlapping Discord requests are needed.
        await self.roles.apply(a, a['mappings'][0], 30, da)
        await self.roles.apply(b, b['mappings'][0], 30, db)
        active = self.repo.assignments(30, link_group_id=a['link_group_id'], guild_id=1)
        print('stale_decisions', {'roles': sorted(self.port.roles), 'active_count': len(active)})
        self.assertEqual(len(active), 1, 'Member lease did not refresh stale linked conflicts')


    async def test_current_absent_reaction_still_removes_role(self):
        a = self.create()
        await self.react(a)
        self.selected.discard(a['message_id'])
        await self.react(a, 'remove')
        self.assertEqual(self.port.roles, set())
        self.assertEqual(self.repo.assignments(30, config_id=a['id']), [])

    async def test_stale_binding_decision_is_rejected_under_member_lease(self):
        a = self.create(behavior='binding')
        da = self.service.decide(a, a['mappings'][0], event='add', user_id=30, member_role_ids=set())
        await self.roles.apply(a, a['mappings'][0], 30, da)
        from discord_io import DiscordFailure
        with self.assertRaises(DiscordFailure):
            await self.roles.apply(a, a['mappings'][0], 30, da)
        self.assertIsNotNone(self.repo.binding_receipt(a['id'], 30))

    async def test_selection_lookup_failure_does_not_remove_role(self):
        a = self.create()
        await self.react(a)
        from discord_io import DiscordFailure
        async def unavailable(*args):
            raise DiscordFailure('rate limited', retry=True)
        self.port.selection_present = unavailable
        with self.assertRaises(DiscordFailure):
            await self.react(a, 'remove')
        self.assertEqual(self.port.roles, {20})

    async def run_removal_jobs(self):
        from jobs import run_batch
        with self.repo.connection() as c:
            c.execute("UPDATE reaction_role_outbox SET state='done' WHERE action NOT IN ('reconcile_remove','reconcile_add')")
            c.execute("UPDATE reaction_role_outbox SET next_attempt_at=0 WHERE action IN ('reconcile_remove','reconcile_add')")
        return await run_batch(self.repo.outbox_jobs, 'rr-removal-test', ReactionRoleDeliveryService(self.repo, self.port).outbox, limit=1)

    async def defer_removal(self, config):
        from discord_io import DiscordFailure
        self.selected.discard(config['message_id'])
        async def unavailable(*args):
            raise DiscordFailure('HTTP 503', retry=True)
        self.port.selection_present = unavailable
        with self.assertRaises(DiscordFailure):
            await self.react(config, 'remove')

    async def test_lookup_503_is_durable_and_recovery_removes_once(self):
        a = self.create()
        await self.react(a)
        await self.defer_removal(a)
        await self.defer_removal(a)
        with self.repo.connection() as c:
            self.assertEqual(c.execute("SELECT count(*) AS n FROM reaction_role_outbox WHERE action='reconcile_remove'").fetchone()['n'], 1)
        self.assertEqual(await self.run_removal_jobs(), 1)
        self.assertEqual(self.port.roles, {20})
        self.port.selection_present = self.selection_present
        calls = []
        original = self.port.role
        async def record(*args, **kwargs):
            calls.append(kwargs['add'])
            await original(*args, **kwargs)
        self.port.role = record
        self.assertEqual(await self.run_removal_jobs(), 1)
        self.assertEqual(self.port.roles, set())
        self.assertEqual(calls, [False])
        self.assertEqual(await self.run_removal_jobs(), 0)

    async def test_deferred_remove_cannot_revoke_new_generation_even_when_currently_absent(self):
        a = self.create()
        await self.react(a)
        await self.defer_removal(a)
        self.port.selection_present = self.selection_present
        await self.react(a)
        self.selected.discard(a['message_id'])
        await self.run_removal_jobs()
        self.assertEqual(self.port.roles, {20})
        self.assertEqual(len(self.repo.assignments(30, config_id=a['id'])), 1)

    async def test_off_does_not_claim_or_exhaust_deferred_remove(self):
        a = self.create()
        await self.react(a)
        await self.defer_removal(a)
        with self.repo.connection() as c:
            c.execute('UPDATE reaction_role_settings SET enabled=0 WHERE guild_id=1')
            c.execute("UPDATE reaction_role_outbox SET attempts=8 WHERE action='reconcile_remove'")
        self.assertEqual(await self.run_removal_jobs(), 0)
        with self.repo.connection() as c:
            row = c.execute("SELECT state,attempts FROM reaction_role_outbox WHERE action='reconcile_remove'").fetchone()
        self.assertEqual((row['state'], row['attempts']), ('pending', 8))
        self.assertEqual(self.port.roles, {20})

    async def test_untracked_removal_job_does_not_adopt_later_assignment(self):
        a = self.create()
        self.port.roles.add(20)
        await self.defer_removal(a)
        self.port.selection_present = self.selection_present
        await self.react(a)
        self.selected.discard(a['message_id'])
        await self.run_removal_jobs()
        self.assertEqual(self.port.roles, {20})

    async def test_reversed_deferred_remove_respects_current_role_capacity(self):
        config = self.create(behavior='reversed')
        mapping = config['mappings'][0]
        mapping['max_members'] = 1
        with self.repo.connection() as c:
            c.execute('UPDATE reaction_role_mappings_v2 SET max_members=1 WHERE id=%s', (mapping['id'],))
        await self.defer_removal(config)
        self.port.selection_present = self.selection_present
        async def full(*args):
            return 1
        self.port.role_member_count = full
        calls = []
        original = self.port.role
        async def record(*args, **kwargs):
            calls.append(kwargs['add'])
            await original(*args, **kwargs)
        self.port.role = record
        await self.run_removal_jobs()
        self.assertEqual(calls, [])

    async def test_off_during_lookup_preserves_role_job_state_and_attempts(self):
        config = self.create()
        await self.react(config)
        await self.defer_removal(config)
        async def turn_off(*args):
            with self.repo.connection() as c:
                c.execute('UPDATE reaction_role_settings SET enabled=0 WHERE guild_id=1')
            return False
        self.port.selection_present = turn_off
        await self.run_removal_jobs()
        self.assertEqual(self.port.roles, {20})
        with self.repo.connection() as c:
            row = c.execute("SELECT state,attempts FROM reaction_role_outbox WHERE action='reconcile_remove'").fetchone()
        self.assertEqual((row['state'], row['attempts']), ('pending', 0))
        with self.repo.connection() as c:
            c.execute('UPDATE reaction_role_settings SET enabled=1 WHERE guild_id=1')
        self.port.selection_present = self.selection_present
        await self.run_removal_jobs()
        self.assertEqual(self.port.roles, set())

    async def test_role_capacity_lease_excludes_other_members_until_commit(self):
        from discord_io import DiscordFailure
        config = self.create()
        with self.repo.connection() as c:
            c.execute('UPDATE reaction_role_mappings_v2 SET max_members=1 WHERE id=%s', (config['mappings'][0]['id'],))
        config = self.repo.message(1, config['id'])
        mapping = config['mappings'][0]
        entered, release = asyncio.Event(), asyncio.Event()
        async def count(*args):
            entered.set()
            await release.wait()
            return 0
        self.port.role_member_count = count
        decision = self.service.decide(config, mapping, event='add', user_id=30, member_role_ids=set())
        first = asyncio.create_task(self.roles.apply(config, mapping, 30, decision))
        await entered.wait()
        try:
            with self.assertRaises(DiscordFailure):
                await self.roles.apply(config, mapping, 31, decision)
        finally:
            release.set()
            await first
        self.assertEqual(self.port.roles, {20})

    async def test_whitelisted_reversed_retry_must_read_capacity(self):
        raw = message(behavior='reversed')
        raw.update(access_policy='whitelist', whitelist_role_ids=[99])
        raw['mappings'][0]['max_members'] = 1
        config = self.service.create(1, raw)
        self.repo.set_discord_message(config['id'], 900 + config['id'])
        config = self.repo.message(1, config['id'])
        self.port.roles = {99}
        await self.defer_removal(config)
        self.port.selection_present = self.selection_present
        counts = []
        async def full(*args):
            counts.append(args)
            return 1
        self.port.role_member_count = full
        await self.run_removal_jobs()
        self.assertNotIn(20, self.port.roles, 'A full role must not be added by whitelisted reversed retry')
        self.assertEqual(len(counts), 1)

    async def test_capacity_busy_remove_must_remain_durable(self):
        from jobs.leases import ResourceLease
        from discord_io import DiscordFailure
        config = self.create()
        await self.react(config)
        self.selected.discard(config['message_id'])
        other = ResourceLease(self.repo.database_url, 'reaction_role_capacity', '1:20')
        other.acquire()
        try:
            with self.assertRaises(DiscordFailure):
                await self.react(config, 'remove')
        finally:
            other.release()
        with self.repo.connection() as c:
            queued = c.execute("SELECT count(*) AS n FROM reaction_role_outbox WHERE action='reconcile_remove'").fetchone()['n']
        self.assertEqual(queued, 1, 'Raw remove lost during another member role operation')

    async def test_capacity_busy_add_is_retried_while_reaction_remains(self):
        from discord_io import DiscordFailure
        from jobs import run_batch
        config = self.create()
        mapping = config['mappings'][0]
        entered, release = asyncio.Event(), asyncio.Event()
        original = self.port.member_role_ids
        async def hold_first(*args):
            entered.set()
            await release.wait()
            return await original(*args)
        self.port.member_role_ids = hold_first
        other_port = Port()
        async def present(*args):
            return True
        other_port.selection_present = present
        other_service = RoleChangeService(self.repo, other_port)
        first_decision = self.service.decide(config, mapping, event='add', user_id=30, member_role_ids=set())
        second_decision = self.service.decide(config, mapping, event='add', user_id=31, member_role_ids=set())
        first = asyncio.create_task(self.roles.apply(config, mapping, 30, first_decision, event='add'))
        await entered.wait()
        try:
            with self.assertRaises(DiscordFailure):
                await other_service.apply(config, mapping, 31, second_decision, event='add')
        finally:
            release.set()
            await first
        with self.repo.connection() as c:
            queued = c.execute("SELECT count(*) AS n FROM reaction_role_outbox WHERE action LIKE 'reconcile_%' AND payload_json::jsonb->>'user_id'='31'").fetchone()['n']
            c.execute("UPDATE reaction_role_outbox SET state='done' WHERE action NOT LIKE 'reconcile_%'")
        self.assertEqual(queued, 1, 'Raw add was lost during another member capacity operation')
        await run_batch(self.repo.outbox_jobs, 'rr-add-contention-test', ReactionRoleDeliveryService(self.repo, other_port).outbox, limit=1)
        self.assertEqual(other_port.roles, {20})
        self.assertEqual(len(self.repo.assignments(30, config_id=config['id'])), 1)
        self.assertEqual(len(self.repo.assignments(31, config_id=config['id'])), 1)

    async def defer_add(self, config):
        from jobs.leases import ResourceLease
        from discord_io import DiscordFailure
        other = ResourceLease(self.repo.database_url, 'reaction_role_capacity', '1:20')
        other.acquire()
        try:
            with self.assertRaises(DiscordFailure):
                await self.react(config, 'add')
        finally:
            other.release()

    async def test_deferred_add_does_not_grant_after_reaction_disappears(self):
        config = self.create()
        await self.defer_add(config)
        self.selected.discard(config['message_id'])
        await self.run_removal_jobs()
        self.assertEqual(self.port.roles, set())
        self.assertEqual(self.repo.assignments(30, config_id=config['id']), [])

    async def test_deferred_add_does_not_adopt_later_generation(self):
        config = self.create()
        await self.defer_add(config)
        await self.react(config)
        generation = self.repo.assignments(30, config_id=config['id'])[0]['generation']
        self.selected.discard(config['message_id'])
        await self.run_removal_jobs()
        current = self.repo.assignments(30, config_id=config['id'])
        self.assertEqual(current[0]['generation'], generation)
        self.assertEqual(self.port.roles, {20})

    async def test_deferred_add_off_during_lookup_preserves_job_attempts(self):
        config = self.create()
        await self.defer_add(config)
        async def turn_off(*args):
            with self.repo.connection() as c:
                c.execute('UPDATE reaction_role_settings SET enabled=0 WHERE guild_id=1')
            return True
        self.port.selection_present = turn_off
        await self.run_removal_jobs()
        with self.repo.connection() as c:
            row = c.execute("SELECT state,attempts FROM reaction_role_outbox WHERE action='reconcile_add'").fetchone()
        self.assertEqual((row['state'], row['attempts']), ('pending', 0))
        self.assertEqual(self.port.roles, set())
        with self.repo.connection() as c:
            c.execute('UPDATE reaction_role_settings SET enabled=1 WHERE guild_id=1')
        self.port.selection_present = self.selection_present
        await self.run_removal_jobs()
        self.assertEqual(self.port.roles, {20})

    async def test_deferred_add_unknown_selection_has_finite_retry(self):
        from discord_io import DiscordFailure
        config = self.create()
        await self.defer_add(config)
        async def forbidden(*args):
            raise DiscordFailure('HTTP 403')
        self.port.selection_present = forbidden
        for _ in range(8):
            await self.run_removal_jobs()
        with self.repo.connection() as c:
            row = c.execute("SELECT state,attempts FROM reaction_role_outbox WHERE action='reconcile_add'").fetchone()
        self.assertEqual((row['state'], row['attempts']), ('failed', 8))
        self.assertEqual(self.port.roles, set())
