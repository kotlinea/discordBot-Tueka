"""Owner transcript completeness and DM send boundary regressions."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from database.testing import temporary_database
from database import transaction
from guild_settings import GuildSettingsRepository
from appeals.repository import AppealRepository
from appeals.delivery import AppealDeliveryService
from appeals.discord_adapter import DiscordAppealAdapter
from cogs.moderation.appeals import AppealsCog
from jobs import LostLease


class AppealReviewBoundaries(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = temporary_database()
        self.url = self.db.__enter__()
        self.addCleanup(self.db.__exit__, None, None, None)
        self.repo = AppealRepository(self.url)
        self.settings = GuildSettingsRepository(self.url)
        self.settings.set_module(1, 'appeals', enabled=True, settings={'retention_days': 1})
        self.item = self.repo.open(1, 10, 100, 'Initial private question')

    async def status(self):
        interaction = SimpleNamespace(user=SimpleNamespace(id=10), response=SimpleNamespace(defer=AsyncMock()), followup=SimpleNamespace(send=AsyncMock()))
        await AppealsCog.status.callback(SimpleNamespace(repository=self.repo), interaction, '1', self.item['id'])
        interaction.followup.send.assert_awaited_once()
        call = interaction.followup.send.call_args
        self.assertTrue(call.kwargs['ephemeral'])
        self.assertEqual(call.kwargs['allowed_mentions'].to_dict()['parse'], [])
        return call

    async def test_short_owner_status_includes_review_reason(self):
        reason = 'Please send the requested evidence.'
        self.repo.transition(1, self.item['id'], 91, 'rejected', reason, revision=1)
        call = await self.status()
        self.assertIn('Initial private question', call.args[0])
        self.assertIn(reason, call.args[0])
        self.assertNotIn('file', call.kwargs)

    async def test_long_owner_status_attaches_complete_history_and_reason(self):
        content = 'CRITICAL_PREFIX_9473:' + 'あ' * 1979
        self.assertEqual(len(content), 2000)
        self.repo.reply(1, self.item['id'], 91, content, revision=1, staff=True)
        for revision in range(2, 13):
            self.repo.reply(1, self.item['id'], 10, f'Followup {revision}', revision=revision)
        reason = 'Independent review reason'
        self.repo.transition(1, self.item['id'], 91, 'accepted', reason, revision=13)
        call = await self.status()
        self.assertLessEqual(len(call.args[0].encode('utf-16-le')) // 2, 2000)
        transcript = call.kwargs['file'].fp.read().decode('utf-8')
        self.assertIn(content, transcript)
        self.assertIn('Initial private question', transcript)
        self.assertIn(reason, transcript)
        for revision in range(2, 13): self.assertIn(f'Followup {revision}', transcript)

    async def test_unicode_status_uses_bounded_content(self):
        content = '😀' * 2000
        self.repo.reply(1, self.item['id'], 91, content, revision=1, staff=True)
        call = await self.status()
        self.assertLessEqual(len(call.args[0].encode('utf-16-le')) // 2, 2000)
        self.assertIn(content, call.kwargs['file'].fp.read().decode('utf-8'))

    async def test_review_reason_survives_more_recent_audit_events(self):
        reason = 'Persisted independent review reason'
        self.repo.transition(1, self.item['id'], 91, 'accepted', reason, revision=1)
        for revision in range(2, 103):
            self.repo.link_ticket(1, self.item['id'], 91, 7, revision)
        call = await self.status()
        self.assertIn(reason, call.args[0])

    async def transport_boundary(self, *, expire=False, recover=False):
        self.repo.reply(1, self.item['id'], 91, 'Private staff reply', revision=1, staff=True)
        if recover:
            with transaction(self.url) as c: c.execute('UPDATE appeal_outbox SET delivery_started=1')
        claim = self.repo.jobs.claim('boundary-worker')
        entered, release = asyncio.Event(), asyncio.Event()
        channel = SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=777)))
        import discord
        async def history(**kwargs):
            yield SimpleNamespace(id=777, author=SimpleNamespace(id=99), embeds=[discord.Embed().set_footer(text=f'Tueka private conversation:{claim.id}')])
        channel.history = history
        user = SimpleNamespace(create_dm=AsyncMock(return_value=channel))
        async def fetch_user(_):
            entered.set()
            await release.wait()
            return user
        bot = SimpleNamespace(fetch_user=fetch_user, user=SimpleNamespace(id=99))
        port = DiscordAppealAdapter(bot, send_allowed=self.repo.delivery_allowed)
        task = asyncio.create_task(AppealDeliveryService(self.repo, port).deliver(claim.payload))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            if expire:
                with transaction(self.url) as c: c.execute('UPDATE appeal_threads SET expires_at=%s WHERE id=%s', (self.item['created_at'], self.item['id']))
            else:
                self.settings.set_module(1, 'appeals', enabled=False)
            release.set()
            if recover:
                outcome = await asyncio.wait_for(task, 5)
                self.assertIsNone(outcome.error)
            else:
                with self.assertRaises(LostLease): await asyncio.wait_for(task, 5)
            channel.send.assert_not_awaited()
            with transaction(self.url) as c: row = c.execute('SELECT * FROM appeal_outbox WHERE id=%s', (claim.id,)).fetchone()
            if recover:
                self.assertEqual(row['discord_message_id'], 777)
            else:
                self.assertEqual(row['attempts'], claim.payload['attempts'])
                self.assertEqual(row['status'], claim.payload['status'])
                self.assertEqual(row['delivery_started'], claim.payload['delivery_started'])
                self.assertIsNone(row['lease_owner'])
                self.assertIsNone(self.repo.jobs.claim('still-paused') if not expire else None)
            return claim
        finally:
            release.set()
            if not task.done():
                task.cancel()
                try: await task
                except asyncio.CancelledError: pass

    async def test_off_after_transport_preparation_blocks_send_and_restores_claim(self):
        await self.transport_boundary()

    async def test_expiry_after_transport_preparation_blocks_send(self):
        await self.transport_boundary(expire=True)

    async def test_off_during_recovery_preserves_receipt_reconciliation(self):
        await self.transport_boundary(recover=True)

    async def test_old_lease_cannot_restore_a_new_claim(self):
        self.repo.reply(1, self.item['id'], 91, 'Private staff reply', revision=1, staff=True)
        old = self.repo.jobs.claim('old-worker')
        with transaction(self.url) as c: c.execute('UPDATE appeal_outbox SET lease_until=0 WHERE id=%s', (old.id,))
        current = self.repo.jobs.claim('new-worker')
        self.assertFalse(self.repo.pause_delivery(old.payload))
        with transaction(self.url) as c: row = c.execute('SELECT * FROM appeal_outbox WHERE id=%s', (old.id,)).fetchone()
        self.assertEqual(row['lease_owner'], current.owner)
        self.assertEqual(row['lease_token'], current.token)
        self.assertEqual(row['attempts'], current.attempt)
