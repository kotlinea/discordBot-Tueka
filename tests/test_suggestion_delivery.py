import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from db_support import prepare_database
from discord_io import DiscordFailure
from guild_settings import GuildSettingsRepository
from jobs import LostLease, Outcome
from suggestions import SuggestionRepository
from suggestions.delivery import SuggestionDeliveryService


class SuggestionPort:
    def __init__(self):
        self.sent = 0
        self.message = None

    async def publish(self, item, settings, *, recover):
        if recover:
            if self.message is None:
                raise DiscordFailure('unknown receipt', partial=True)
            return self.message
        self.sent += 1
        self.message = 900
        return 900


class SuggestionDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        database = prepare_database(Path(self.temp.name) / 'suggestions.db', self.addCleanup)
        self.repo = SuggestionRepository(database)
        settings = GuildSettingsRepository(database)
        settings.set_module(1, 'suggestions', enabled=True, settings={'channel_id': 10})
        self.port = SuggestionPort()
        self.service = SuggestionDeliveryService(self.repo, settings, self.port)
        self.item = self.repo.create(1, 10, 20, {'idea': 'A proposal'})

    async def test_database_failure_after_send_recovers_without_duplicate_post(self):
        now = 1000
        self.repo.outbox_jobs.clock = lambda: now
        # The real creation timestamp must be due at our deterministic lease clock.
        with patch('suggestions.repository.time.time', return_value=1000):
            self.item = self.repo.create(1, 10, 20, {'idea': 'Retry'})
            claim = self.repo.outbox_jobs.claim('worker', lease_seconds=3)
            with patch.object(self.repo, 'publication_delivered', side_effect=RuntimeError('database unavailable')):
                with self.assertRaises(RuntimeError):
                    await self.service.deliver(claim.payload)
        now = 1004
        with patch('suggestions.repository.time.time', return_value=1004):
            retry = self.repo.outbox_jobs.claim('worker')
            self.assertEqual(retry.id, claim.id)
            self.assertIsNone((await self.service.deliver(retry.payload)).error)
            self.assertTrue(self.repo.outbox_jobs.finish(retry, Outcome()))
        self.assertEqual(self.port.sent, 1)
        self.assertEqual(self.repo.get(1, self.item['id'])['message_id'], 900)

    async def test_stale_lease_cannot_attach_message_or_change_delivery_state(self):
        self.repo.outbox_jobs.clock = lambda: self.item['created_at']
        claim = self.repo.outbox_jobs.claim('worker', lease_seconds=3)
        self.repo.outbox_jobs.clock = lambda: claim.payload['created_at'] + 4
        newer = self.repo.outbox_jobs.claim('worker')
        self.assertEqual(newer.id, claim.id)
        with self.assertRaises(LostLease):
            self.repo.publication_delivered(claim.payload, 999)
        with self.assertRaises(LostLease):
            self.repo.delivery_state(claim.payload, started=False, failed='old attempt')
        self.assertIsNone(self.repo.get(1, self.item['id'])['message_id'])
        self.assertEqual(self.repo.get(1, self.item['id'])['status'], 'pending')

    async def test_missing_receipt_is_not_resent(self):
        claim = self.repo.outbox_jobs.claim('worker')
        self.repo.delivery_state(claim.payload, started=True)
        self.repo.outbox_jobs.finish(claim, Outcome('crashed', retry=True))
        self.repo.outbox_jobs.clock = lambda: claim.payload['created_at'] + 100
        retry = self.repo.outbox_jobs.claim('worker')
        result = await self.service.deliver(retry.payload)
        self.assertTrue(result.retry)
        self.assertEqual(self.port.sent, 0)

    async def test_conflicting_publication_reference_is_not_success_or_overwritten(self):
        claim = self.repo.outbox_jobs.claim('worker')
        self.repo.attach_message(1, self.item['id'], 800)
        with self.assertRaises(DiscordFailure):
            self.repo.publication_delivered(claim.payload, 900)
        self.assertEqual(self.repo.get(1, self.item['id'])['message_id'], 800)

    async def test_recovered_failed_publication_enqueues_presentation_refresh(self):
        claim = self.repo.outbox_jobs.claim('worker')
        self.repo.delivery_state(claim.payload, started=True, failed='receipt unavailable')
        self.port.message = 900
        job = {**claim.payload, 'delivery_started': True}
        self.assertIsNone((await self.service.deliver(job)).error)
        self.assertEqual(self.repo.get(1, self.item['id'])['status'], 'pending')
        with self.repo._connection() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) AS count FROM suggestion_outbox WHERE action='sync'").fetchone()["count"], 1)
        self.assertEqual(self.port.sent, 0)
