"""Known Gateway gaps must survive best-effort observer cleanup failures."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from db_support import prepare_database
from cogs.community.insights import InsightsCog
from insights.models import DAY, day_key
from insights.repository import InsightsRepository
from insights.service import InsightsService


class InsightsFinalReviewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.url = prepare_database(Path(temporary.name) / 'insights-final-review', self.addCleanup)
        self.now = DAY * 20000 + 1000
        self.repository = InsightsRepository(self.url, clock=lambda: self.now)
        self.repository.settings.set_module(1, 'insights', enabled=True, settings={
            'channel_ids': [20], 'retention_days': 30, 'track_members': True,
        })
        self.repository.claim(1, 'observer')
        self.repository.heartbeat(1, 'observer', {30: 20})
        self.guild = SimpleNamespace(id=1, unavailable=False)
        self.cog = object.__new__(InsightsCog)
        self.cog.repository = self.repository
        self.cog.service = InsightsService(self.repository, owner='observer')
        self.cog.bot = SimpleNamespace(is_ready=lambda: True, guilds=[self.guild])
        self.cog._snapshot = lambda guild: {30: 20}
        self.cog._claimed = {1}
        self.cog._ready = True

    def assert_seconds(self, expected):
        today = day_key(self.now)
        values = self.repository.report(1, today, today)['days'][0]
        self.assertEqual(values['observed_seconds'], expected)
        self.assertEqual(values['voice_seconds'], expected)

    async def test_ready_and_resumed_reclaim_after_failed_disconnect_release(self):
        for event in ('on_ready', 'on_resumed'):
            with self.subTest(event=event):
                self.now += 10
                with patch.object(self.cog.service, 'release', side_effect=ConnectionError('synthetic')):
                    await self.cog.on_disconnect()
                    self.assertEqual(self.cog._claimed, set())
                    self.assertFalse(self.cog._can_observe(self.guild))
                    self.now += 20
                    await getattr(self.cog, event)()
                self.assert_seconds(0)
                self.now += 10
                await self.cog.collect()
                # Repeated snapshots at the same instant must not duplicate time.
                await self.cog.collect()
                self.assert_seconds(10)
                # Start the second subcase with a fresh, empty observation day.
                self.now += DAY
                self.repository.claim(1, 'observer')
                self.repository.heartbeat(1, 'observer', {30: 20})

    async def test_observation_waits_for_database_recovery_and_successful_claim(self):
        recovered = asyncio.Event()
        claim = self.cog.service.claim

        def claim_when_recovered(guild):
            if not recovered.is_set():
                raise ConnectionError('synthetic')
            return claim(guild)

        self.now += 10
        with patch.object(self.cog.service, 'release', side_effect=ConnectionError('synthetic')):
            await self.cog.on_disconnect()
        self.now += 20
        with patch.object(self.cog.service, 'claim', side_effect=claim_when_recovered):
            await self.cog.on_resumed()
            self.assertFalse(self.cog._can_observe(self.guild))
            self.assert_seconds(0)
            self.now += 10
            recovered.set()
            await self.cog.collect()
            self.assertTrue(self.cog._can_observe(self.guild))
            self.assert_seconds(0)
            self.now += 10
            await self.cog.collect()
            self.assert_seconds(10)

    async def test_ready_alone_reestablishes_boundary_when_release_fails(self):
        self.now += 30
        with patch.object(self.cog.service, 'release', side_effect=ConnectionError('synthetic')):
            await self.cog.on_ready()
        self.assertTrue(self.cog._can_observe(self.guild))
        self.assert_seconds(0)

    async def test_reclaim_does_not_steal_another_live_observer(self):
        self.now += 10
        await self.cog.on_disconnect()
        self.assertTrue(self.repository.claim(1, 'other-observer'))
        self.repository.heartbeat(1, 'other-observer', {30: 20})
        self.now += 20
        await self.cog.on_resumed()
        self.assertFalse(self.cog._can_observe(self.guild))
        self.assert_seconds(0)
        self.assertTrue(self.repository.heartbeat(1, 'other-observer', {30: 20}))
        self.assert_seconds(20)

    async def test_unavailable_guild_discards_claim_even_if_release_fails(self):
        self.now += 10
        self.guild.unavailable = True
        with patch.object(self.cog.service, 'release', side_effect=ConnectionError('synthetic')):
            await self.cog.collect()
        self.assertEqual(self.cog._claimed, set())
        self.now += 20
        self.guild.unavailable = False
        await self.cog.collect()
        self.assert_seconds(0)
