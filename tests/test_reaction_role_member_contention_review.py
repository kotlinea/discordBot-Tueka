"""Gateway intent must survive a real outbox handler owning the same member."""
import asyncio
import tempfile
import unittest
from pathlib import Path

from db_support import prepare_database
from discord_io import DiscordFailure
from jobs import run_batch
from reaction_roles.delivery import ReactionRoleDeliveryService
from reaction_roles.repository import ReactionRoleRepository
from reaction_roles.roles import RoleChangeService
from reaction_roles.service import ReactionRoleService
from test_reaction_role_review_boundaries import Port
from test_reaction_roles import message


class SelectionPort(Port):
    def __init__(self):
        super().__init__()
        self.selected = set()
        self.cleanup_entered = asyncio.Event()
        self.cleanup_release = asyncio.Event()

    async def selection_present(self, guild_id, channel_id, message_id, emoji, user_id):
        return message_id in self.selected

    async def remove_selection(self, guild_id, channel_id, message_id, emoji, user_id):
        self.cleanup_entered.set()
        await self.cleanup_release.wait()
        self.selected.discard(message_id)
        await super().remove_selection(guild_id, channel_id, message_id, emoji, user_id)


class ReactionRoleMemberContentionReviewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = ReactionRoleRepository(prepare_database(Path(temp.name) / 'rr', self.addCleanup))
        self.service = ReactionRoleService(self.repo)
        self.port = SelectionPort()
        self.roles = RoleChangeService(self.repo, self.port)
        self.delivery = ReactionRoleDeliveryService(self.repo, self.port)

    def create(self, **kwargs):
        created = self.service.create(1, message(**kwargs))
        self.repo.set_discord_message(created['id'], 900 + created['id'])
        return self.repo.message(1, created['id'])

    async def raw(self, config, event):
        if event == 'add':
            self.port.selected.add(config['message_id'])
        else:
            self.port.selected.discard(config['message_id'])
        decision = self.service.decide(config, config['mappings'][0], event=event,
            user_id=30, member_role_ids=set(self.port.roles))
        await self.roles.apply(config, config['mappings'][0], 30, decision, event=event)

    async def contend(self, event):
        target = self.create()
        if event == 'remove':
            await self.raw(target, 'add')
        # A successful verify selection normally reserves clear_selection.
        owner_config = self.create(behavior='verify', role_id=21, channel_id=11)
        await self.raw(owner_config, 'add')
        with self.repo.connection() as c:
            c.execute("UPDATE reaction_role_outbox SET state='done' WHERE action!='clear_selection'")
        owner = asyncio.create_task(run_batch(self.repo.outbox_jobs, 'member-owner',
            self.delivery.outbox, limit=1))
        try:
            await asyncio.wait_for(self.port.cleanup_entered.wait(), timeout=5)
            try:
                await self.raw(target, event)
            except DiscordFailure:
                # Gateway caller records failure but does not retry the event.
                # Convergence must come from the durable delivery path.
                pass
        finally:
            self.port.cleanup_release.set()
            await owner
        with self.repo.connection() as c:
            c.execute("UPDATE reaction_role_outbox SET next_attempt_at=0 WHERE action IN ('reconcile_add','reconcile_remove')")
        await run_batch(self.repo.outbox_jobs, 'member-reconcile', self.delivery.outbox)
        assignments = self.repo.assignments(30, config_id=target['id'])
        self.assertEqual(20 in self.port.roles, event == 'add',
            'Gateway selection did not converge after outbox member ownership ended')
        self.assertEqual(bool(assignments), event == 'add')
        self.assertIn(21, self.port.roles)

    async def test_raw_remove_during_clear_selection_converges_after_owner_release(self):
        await self.contend('remove')

    async def test_raw_add_during_clear_selection_converges_after_owner_release(self):
        await self.contend('add')

    async def pending_add_then_remove(self, *, newer_selection=False):
        target = self.create()
        entered, release = asyncio.Event(), asyncio.Event()
        original = self.port.role
        async def hold_after_discord(*args, **kwargs):
            await original(*args, **kwargs)
            if kwargs['add']:
                entered.set()
                await release.wait()
        self.port.role = hold_after_discord
        owner = asyncio.create_task(self.raw(target, 'add'))
        await entered.wait()
        try:
            with self.assertRaises(DiscordFailure):
                await self.raw(target, 'remove')
        finally:
            release.set()
            await owner
        self.port.role = original
        if newer_selection:
            await self.raw(target, 'add')
            self.port.selected.discard(target['message_id'])
        with self.repo.connection() as c:
            c.execute("UPDATE reaction_role_outbox SET state='done' WHERE action NOT LIKE 'reconcile_%'")
        await run_batch(self.repo.outbox_jobs, 'pending-owner-reconcile', self.delivery.outbox)
        return target

    async def test_remove_during_pending_add_adopts_predecessor_commit(self):
        target = await self.pending_add_then_remove()
        self.assertNotIn(20, self.port.roles)
        self.assertEqual(self.repo.assignments(30, config_id=target['id']), [])

    async def test_old_member_notification_cannot_touch_later_generation(self):
        target = await self.pending_add_then_remove(newer_selection=True)
        self.assertIn(20, self.port.roles)
        self.assertEqual(len(self.repo.assignments(30, config_id=target['id'])), 1)

    async def remove_before_owner_operation(self, *, newer_selection=False):
        target = self.create()
        entered, release = asyncio.Event(), asyncio.Event()
        original = self.port.member_role_ids

        async def hold_before_operation(*args, **kwargs):
            entered.set()
            await release.wait()
            return await original(*args, **kwargs)

        self.port.member_role_ids = hold_before_operation
        owner = asyncio.create_task(self.raw(target, 'add'))
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            self.assertEqual(self.repo.pending_role_changes(1), [])
            with self.assertRaises(DiscordFailure):
                await self.raw(target, 'remove')
        finally:
            release.set()
            await owner
            self.port.member_role_ids = original
        if newer_selection:
            await self.raw(target, 'add')
            self.port.selected.discard(target['message_id'])
        with self.repo.connection() as c:
            c.execute("UPDATE reaction_role_outbox SET state='done' WHERE action NOT LIKE 'reconcile_%'")
        await run_batch(self.repo.outbox_jobs, 'pre-operation-reconcile', self.delivery.outbox)
        return target

    async def test_remove_before_owner_operation_is_recorded_survives_owner_commit(self):
        target = await self.remove_before_owner_operation()
        self.assertNotIn(20, self.port.roles,
            'A remove queued before the owner records its operation must survive that owner commit')
        self.assertEqual(self.repo.assignments(30, config_id=target['id']), [])

    async def test_before_operation_notification_cannot_adopt_next_owner_generation(self):
        target = await self.remove_before_owner_operation(newer_selection=True)
        self.assertIn(20, self.port.roles)
        self.assertEqual(len(self.repo.assignments(30, config_id=target['id'])), 1)

    async def test_owner_changes_between_acquire_failure_and_enqueue_cannot_adopt_successor(self):
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch
        from jobs.leases import ResourceLease
        target = self.create()
        await self.raw(target, 'add')
        old_generation = self.repo.assignments(30, config_id=target['id'])[0]['generation']
        first_owner = ResourceLease(self.repo.database_url, 'reaction_role_member', '1:30')
        first_owner.acquire()
        original = self.repo.queue_member_reconciliation
        successor_generation = []

        def switch_owner_before_enqueue(*args, **kwargs):
            first_owner.release()
            # Run a complete later owner on its own event loop while this raw
            # callback is paused between acquisition failure and durable enqueue.
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(lambda: asyncio.run(self.raw(target, 'add'))).result(timeout=10)
            successor_generation.append(self.repo.assignments(30, config_id=target['id'])[0]['generation'])
            self.port.selected.discard(target['message_id'])
            return original(*args, **kwargs)

        try:
            with patch.object(self.repo, 'queue_member_reconciliation', side_effect=switch_owner_before_enqueue):
                with self.assertRaises(DiscordFailure):
                    await self.raw(target, 'remove')
        finally:
            first_owner.release()
        self.assertGreater(successor_generation[0], old_generation)
        with self.repo.connection() as c:
            c.execute("UPDATE reaction_role_outbox SET state='done' WHERE action NOT LIKE 'reconcile_%'")
        await run_batch(self.repo.outbox_jobs, 'owner-switch-reconcile', self.delivery.outbox)
        self.assertIn(20, self.port.roles,
            'The failed acquire must identify its actual competing owner, not an owner observed later at enqueue')
        self.assertEqual(self.repo.assignments(30, config_id=target['id'])[0]['generation'], successor_generation[0])
