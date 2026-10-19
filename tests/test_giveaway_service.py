import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from db_support import prepare_database
from database import transaction
from giveaways.repository import GiveawayRepository
from giveaways.service import GiveawayService
from discord_io import DiscordFailure
from jobs import run_batch


class GeneratedPort:
    def __init__(self):
        self.members = {user: {'id': user, 'guild_id': 1, 'bot': False, 'role_ids': [], 'created_at': 0, 'joined_at': 0} for user in (30, 31, 32)}
        self.sent = []
        self.edited = []
        self.unknown = False
        self.discoverable = True
        self.fetch_failure = None

    async def member(self, guild, user):
        if self.fetch_failure and user == 31:
            raise self.fetch_failure
        return self.members.get(user)

    async def send(self, plan, marker):
        self.sent.append(100)
        if self.unknown:
            raise DiscordFailure('Generated response loss', retry=True, partial=True)
        return 100

    async def reconcile(self, guild, channel, marker):
        return 100 if self.discoverable else None

    async def edit(self, plan, message, marker):
        self.edited.append(message)


class GiveawayServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.url = prepare_database(Path(self.tmp.name) / 'giveaway-service', self.addCleanup)
        self.now = 500000
        self.repo = GiveawayRepository(self.url, clock=lambda: self.now)
        self.repo.settings.set_module(1, 'giveaways', enabled=True)
        self.item = self.repo.create(1, 10, {'title': 'Generated', 'channel_id': 20, 'ends_at': self.now + 60}, 'generated')
        self.item = self.repo.launch(1, self.item['id'], 10, self.item['revision'])
        self.port = GeneratedPort()
        self.service = GiveawayService(self.repo, self.port)

    async def publish(self):
        await run_batch(self.repo.jobs, 'publisher', self.service.publish, limit=1)

    async def enter(self, user):
        return await self.service.participate(1, self.item['id'], user, 100, user * 10, join=True)

    async def test_join_checks_live_identity_and_rechecks_membership_at_draw(self):
        await self.publish()
        await self.enter(30)
        await self.enter(31)
        self.port.members.pop(31)
        self.now += 60
        await run_batch(self.repo.draw_jobs, 'draw', self.service.draw)
        draws = self.repo.history(1, self.item['id'])['draws']
        self.assertEqual(json.loads(draws[0]['candidates_json']), [30])
        self.assertEqual(draws[0]['excluded_count'], 1)

    async def test_partial_membership_fetch_never_commits_partial_draw(self):
        await self.publish()
        await self.enter(30)
        await self.enter(31)
        self.now += 60
        self.port.fetch_failure = DiscordFailure('Generated throttle', retry=True)
        await run_batch(self.repo.draw_jobs, 'draw', self.service.draw, limit=1)
        self.assertEqual(self.repo.history(1, self.item['id'])['draws'], [])
        self.assertEqual(self.repo.item(1, self.item['id'])['status'], 'closing')
        self.port.fetch_failure = None
        self.now += 1000
        await run_batch(self.repo.draw_jobs, 'draw', self.service.draw)
        self.assertEqual(len(self.repo.history(1, self.item['id'])['draws']), 1)

    async def test_unknown_send_reconciles_without_duplicate_publication(self):
        self.port.unknown = True
        await self.publish()
        self.now += 1000
        await self.publish()
        self.assertEqual(self.port.sent, [100])
        self.assertEqual(self.port.edited, [100])
        self.assertEqual(self.repo.item(1, self.item['id'])['message_id'], 100)

    async def test_unrecoverable_unknown_send_stops_without_blind_resend(self):
        self.port.unknown = True
        await self.publish()
        self.port.discoverable = False
        self.now += 1000
        await self.publish()
        self.now += 1000
        await self.publish()
        self.assertEqual(self.port.sent, [100])
        self.assertIsNone(self.repo.item(1, self.item['id'])['message_id'])

    async def test_membership_scope_and_bot_rejection_allow_no_entry(self):
        await self.publish()
        for key, value in (('bot', True), ('guild_id', 2), ('id', 999)):
            original = self.port.members[30].copy()
            self.port.members[30][key] = value
            with self.assertRaises(PermissionError):
                await self.enter(30)
            self.port.members[30] = original
        self.assertEqual(self.repo.history(1, self.item['id'])['entries'], [])

    async def test_unexpected_exception_text_is_not_saved(self):
        await self.publish()
        await self.enter(31)
        self.now += 60
        self.port.fetch_failure = RuntimeError('Generated private credential text')
        claim = self.repo.draw_jobs.claim('draw')
        result = await self.service.draw(claim.payload)
        self.assertTrue(result.retry)
        self.assertNotIn('private', result.error)
        self.assertIn('RuntimeError', result.error)

    async def test_cancel_after_settled_before_finish_keeps_one_durable_followup(self):
        claim = self.repo.jobs.claim('first-publisher')
        outcome = await self.service.publish(claim.payload)
        self.assertIsNone(outcome.error)
        await self.enter(30)
        await self.enter(31)
        current = self.repo.item(1, self.item['id'])
        self.repo.cancel(1, current['id'], 10, current['revision'], 'Generated cancellation')
        with transaction(self.url) as c:
            self.assertEqual([r['status'] for r in c.execute('SELECT status FROM giveaway_outbox ORDER BY id')],
                ['processing', 'pending'])
        self.assertTrue(self.repo.jobs.finish(claim, outcome))
        self.repo = GiveawayRepository(self.url, clock=lambda: self.now)
        self.service = GiveawayService(self.repo, self.port)
        self.port.edit = AsyncMock(wraps=self.port.edit)
        await self.publish()
        self.assertEqual(self.port.edit.call_args.args[0]['campaign']['status'], 'cancelled')
        self.assertEqual(self.port.sent, [100])
        self.assertEqual(self.port.edited, [100])
        self.assertIsNone(self.repo.jobs.claim('empty'))

    async def test_draw_after_settled_before_finish_publishes_persisted_result(self):
        await self.publish()
        await self.enter(30)
        claim = self.repo.jobs.claim('first-publisher', lease_seconds=120)
        outcome = await self.service.publish(claim.payload)
        self.assertIsNone(outcome.error)
        self.now += 60
        await run_batch(self.repo.draw_jobs, 'drawer', self.service.draw, limit=1)
        self.assertEqual(self.repo.item(1, self.item['id'])['status'], 'closed')
        with transaction(self.url) as c:
            self.assertEqual([r['status'] for r in c.execute('SELECT status FROM giveaway_outbox ORDER BY id')],
                ['completed', 'processing', 'pending'])
        self.assertTrue(self.repo.jobs.finish(claim, outcome))
        self.repo = GiveawayRepository(self.url, clock=lambda: self.now)
        self.service = GiveawayService(self.repo, self.port)
        self.port.edit = AsyncMock(wraps=self.port.edit)
        await self.publish()
        plan = self.port.edit.call_args.args[0]
        self.assertEqual(plan['campaign']['status'], 'closed')
        self.assertEqual(json.loads(plan['draw']['winners_json']), [30])
        self.assertEqual(len(self.repo.history(1, self.item['id'])['draws']), 1)
        self.assertEqual(self.port.sent, [100])
        self.assertIsNone(self.repo.jobs.claim('empty'))
