"""An existing social delivery intent survives a guild's temporary module pause."""
import tempfile
import time
import unittest
from pathlib import Path

from database import transaction
from discord_io import DiscordFailure
from db_support import prepare_database
from guild_settings import GuildSettingsRepository
from jobs import run_batch
from social import SocialRepository
from social.models import default_templates
from social.service import SocialDeliveryService


class ReceiptPort:
    def __init__(self):
        self.calls = []

    def available(self, guild_id, channel_id):
        return True

    async def send(self, guild_id, channel_id, content, embed, role_id, receipt_key, *, recover, created_at):
        self.calls.append((guild_id, channel_id, recover))
        return 900 + guild_id

    async def edit(self, *args):
        raise AssertionError('The post notification must use send')


class SocialPauseReviewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.url = prepare_database(Path(directory.name) / 'pause.db', self.addCleanup)
        self.repository = SocialRepository(self.url)
        self.settings = GuildSettingsRepository(self.url)
        self.port = ReceiptPort()
        self.service = SocialDeliveryService(self.repository, self.settings, self.port)
        self.key = 'youtube:video:pause-review'

    def subscription(self, guild):
        self.settings.set_module(guild, 'youtube_updates', enabled=True)
        return self.repository.save_social_subscription_v2(guild, 'youtube', 'creator', 10 + guild,
            ['video'], {}, default_templates('youtube'))

    def event(self, *, attempts=2):
        self.repository.enqueue_social_event_v2('youtube', 'pause-review', 'creator', 'video', {'account': 'creator'})
        with transaction(self.url) as connection:
            connection.execute("UPDATE social_events SET status='retry',attempts=%s,available_at=%s,last_error='temporary delivery error' WHERE event_key=%s",
                (attempts, int(time.time()) - 1, self.key))

    def state(self):
        with transaction(self.url) as connection:
            return dict(connection.execute('SELECT status,attempts,available_at,processed_at,last_error,lease_owner,lease_token,lease_until FROM social_events WHERE event_key=%s', (self.key,)).fetchone())

    async def run_event(self):
        return await run_batch(self.repository.event_jobs, 'pause-review', self.service.deliver_outcome, limit=1)

    async def test_retry_and_uncertain_intents_preserve_event_attempts_while_off_then_resume(self):
        subscription = self.subscription(1)
        self.event()
        self.repository.record_social_delivery(subscription['id'], self.key, 11, None, 'pending')
        for state in ('retry', 'uncertain', 'pending'):
            with self.subTest(state=state):
                with transaction(self.url) as connection:
                    connection.execute("UPDATE social_events SET status='retry',attempts=2,processed_at=NULL,available_at=%s WHERE event_key=%s", (int(time.time()) - 1, self.key))
                    connection.execute('UPDATE social_deliveries SET state=%s,next_attempt_at=0 WHERE subscription_id=%s AND event_key=%s', (state, subscription['id'], self.key))
                self.settings.set_module(1, 'youtube_updates', enabled=False)
                before = self.state()
                receipt = self.repository.social_delivery(subscription['id'], self.key)
                for _ in range(10):
                    await self.run_event()
                self.assertEqual(self.state(), before)
                self.assertEqual(self.repository.social_delivery(subscription['id'], self.key), receipt)
                self.assertEqual(self.port.calls, [])
                self.settings.set_module(1, 'youtube_updates', enabled=True)
                await self.run_event()
                self.assertEqual(self.state()['status'], 'completed')
                self.assertEqual(self.repository.social_delivery(subscription['id'], self.key)['state'], 'sent')
                self.assertEqual(self.port.calls, [(1, 11, state in {'pending', 'uncertain'})])
                self.port.calls.clear()

    async def test_shared_event_keeps_paused_intent_after_other_guild_was_sent(self):
        sent, paused = self.subscription(1), self.subscription(2)
        self.event()
        self.repository.record_social_delivery(sent['id'], self.key, 11, 901, 'sent')
        self.repository.record_social_delivery(paused['id'], self.key, 12, None, 'pending')
        self.repository.fail_social_delivery(paused['id'], self.key, 'temporary failure', retry=True)
        with transaction(self.url) as connection:
            connection.execute('UPDATE social_deliveries SET next_attempt_at=0 WHERE subscription_id=%s', (paused['id'],))
        self.settings.set_module(2, 'youtube_updates', enabled=False)
        before = self.state()
        for _ in range(10):
            await self.run_event()
        self.assertEqual(self.state(), before)
        self.assertEqual(self.port.calls, [])
        self.settings.set_module(2, 'youtube_updates', enabled=True)
        await self.run_event()
        self.assertEqual(self.port.calls, [(2, 12, False)])
        self.assertEqual(self.state()['status'], 'completed')

    async def test_new_event_while_off_without_an_intent_is_suppressed(self):
        subscription = self.subscription(1)
        self.event(attempts=0)
        self.settings.set_module(1, 'youtube_updates', enabled=False)
        await self.run_event()
        self.assertEqual(self.state()['status'], 'completed')
        self.assertEqual(self.repository.social_delivery(subscription['id'], self.key)['state'], 'skipped')
        self.settings.set_module(1, 'youtube_updates', enabled=True)
        await self.run_event()
        self.assertEqual(self.port.calls, [])

    async def test_off_intent_does_not_exhaust_a_crashed_final_attempt(self):
        subscription = self.subscription(1)
        self.event(attempts=8)
        self.repository.record_social_delivery(subscription['id'], self.key, 11, None, 'uncertain')
        self.settings.set_module(1, 'youtube_updates', enabled=False)
        before = self.state()
        await self.run_event()
        self.assertEqual(self.state(), before)
        self.assertEqual(self.port.calls, [])
        self.settings.set_module(1, 'youtube_updates', enabled=True)
        await self.run_event()
        self.assertEqual(self.state()['status'], 'failed')
        self.assertEqual(self.state()['attempts'], 8)
        self.assertEqual(self.port.calls, [])

    async def test_active_unsent_guild_proceeds_while_other_intent_is_paused(self):
        active, paused = self.subscription(1), self.subscription(2)
        self.event()
        self.repository.record_social_delivery(paused['id'], self.key, 12, None, 'uncertain')
        self.settings.set_module(2, 'youtube_updates', enabled=False)
        before = self.state()
        await self.run_event()
        self.assertEqual(self.port.calls, [(1, 11, False)])
        self.assertEqual(self.repository.social_delivery(active['id'], self.key)['state'], 'sent')
        self.assertEqual(self.state(), before)
        for _ in range(10):
            await self.run_event()
        self.assertEqual(self.port.calls, [(1, 11, False)])
        self.assertEqual(self.state(), before)
        self.settings.set_module(2, 'youtube_updates', enabled=True)
        await self.run_event()
        self.assertEqual(self.port.calls, [(1, 11, False), (2, 12, True)])
        self.assertEqual(self.state()['status'], 'completed')

    async def test_disable_after_claim_preserves_attempt_and_reenable_before_finish_wakes(self):
        subscription = self.subscription(1)
        self.event()
        self.repository.record_social_delivery(subscription['id'], self.key, 11, None, 'uncertain')
        before = self.state()

        async def pause_during_processing(event):
            self.settings.set_module(1, 'youtube_updates', enabled=False)
            outcome = await self.service.deliver_outcome(event)
            self.assertEqual(self.port.calls, [])
            self.settings.set_module(1, 'youtube_updates', enabled=True)
            return outcome

        await run_batch(self.repository.event_jobs, 'pause-review', pause_during_processing, limit=1)
        self.assertEqual(self.state(), before)
        await self.run_event()
        self.assertEqual(self.port.calls, [(1, 11, True)])
        self.assertEqual(self.state()['status'], 'completed')

    async def test_disable_after_intent_before_external_send_keeps_pending(self):
        self.subscription(1)
        self.event(attempts=0)
        before = self.state()
        original = self.repository.record_social_delivery

        def record_then_disable(*args, **kwargs):
            recorded = original(*args, **kwargs)
            self.settings.set_module(1, 'youtube_updates', enabled=False)
            return recorded

        from unittest.mock import patch
        with patch.object(self.repository, 'record_social_delivery', side_effect=record_then_disable):
            await self.run_event()
        self.assertEqual(self.state(), before)
        self.assertEqual(self.port.calls, [])
        self.settings.set_module(1, 'youtube_updates', enabled=True)
        await self.run_event()
        self.assertEqual(self.port.calls, [(1, 11, True)])
        self.assertEqual(self.state()['status'], 'completed')

    async def test_new_off_recipient_stays_suppressed_while_shared_event_is_paused(self):
        delivered, paused, suppressed = (self.subscription(guild) for guild in (1, 2, 3))
        self.event()
        self.repository.record_social_delivery(delivered['id'], self.key, 11, 901, 'sent')
        self.repository.record_social_delivery(paused['id'], self.key, 12, None, 'uncertain')
        self.settings.set_module(2, 'youtube_updates', enabled=False)
        self.settings.set_module(3, 'youtube_updates', enabled=False)
        await self.run_event()
        self.assertEqual(self.port.calls, [])
        self.settings.set_module(3, 'youtube_updates', enabled=True)
        await self.run_event()
        self.assertEqual(self.port.calls, [], 'A notification observed while OFF must not be replayed on re-enabling')
        self.assertNotEqual(self.state()['status'], 'completed')
        self.settings.set_module(2, 'youtube_updates', enabled=True)
        await self.run_event()
        self.assertEqual(self.port.calls, [(2, 12, True)])
        self.assertEqual(self.state()['status'], 'completed')
        self.assertNotEqual(self.repository.social_delivery(suppressed['id'], self.key)['state'], 'sent')

    async def test_terminal_receipts_outlive_retention_while_event_can_still_resume(self):
        terminals = [self.subscription(guild) for guild in (1, 2, 3)]
        paused = self.subscription(4)
        self.event()
        self.repository.record_social_delivery(paused['id'], self.key, 14, None, 'uncertain')
        self.settings.set_module(4, 'youtube_updates', enabled=False)
        now = int(time.time())
        expired = now - 30 * 86400 - 1
        for subscription, state in zip(terminals, ('sent', 'failed', 'skipped')):
            self.repository.record_social_delivery(subscription['id'], self.key,
                subscription['channel_id'], 901 if state == 'sent' else None, state)
        with transaction(self.url) as connection:
            connection.execute('UPDATE social_deliveries SET updated_at=%s WHERE subscription_id<>%s', (expired, paused['id']))
        self.repository.purge_social_history(retention_days=30)
        for subscription in terminals:
            self.assertIsNotNone(self.repository.social_delivery(subscription['id'], self.key),
                'A live event still uses terminal receipts to prevent duplicate sends')
        self.settings.set_module(4, 'youtube_updates', enabled=True)
        await self.run_event()
        self.assertEqual(self.port.calls, [(4, 14, True)])
        self.repository.purge_social_history(retention_days=30)
        for subscription in terminals:
            self.assertIsNotNone(self.repository.social_delivery(subscription['id'], self.key))
        with transaction(self.url) as connection:
            connection.execute('UPDATE social_events SET processed_at=%s WHERE event_key=%s', (expired, self.key))
        self.repository.purge_social_history(retention_days=30)
        for subscription in terminals:
            self.assertIsNone(self.repository.social_delivery(subscription['id'], self.key))

    async def test_active_final_retry_does_not_exhaust_another_guilds_paused_intent(self):
        active, paused, sent = (self.subscription(guild) for guild in (1, 2, 3))
        self.event(attempts=7)
        self.repository.record_social_delivery(active['id'], self.key, 11, None, 'retry')
        self.repository.record_social_delivery(paused['id'], self.key, 12, None, 'uncertain')
        self.repository.record_social_delivery(sent['id'], self.key, 13, 903, 'sent')
        with transaction(self.url) as connection:
            connection.execute('UPDATE social_deliveries SET attempts=7,next_attempt_at=0 WHERE subscription_id=%s', (active['id'],))
        self.settings.set_module(2, 'youtube_updates', enabled=False)
        paused_before = self.repository.social_delivery(paused['id'], self.key)
        attempts = []
        original_send = self.port.send

        async def fail_active(guild_id, *args, **kwargs):
            if guild_id == 1:
                attempts.append(guild_id)
                raise DiscordFailure('temporary Discord failure', retry=True)
            return await original_send(guild_id, *args, **kwargs)

        from unittest.mock import patch
        with patch.object(self.port, 'send', side_effect=fail_active):
            await self.run_event()
            self.assertEqual(attempts, [1])
            self.assertEqual(self.repository.social_delivery(paused['id'], self.key), paused_before)
            for _ in range(10):
                with transaction(self.url) as connection:
                    connection.execute('UPDATE social_events SET available_at=0 WHERE event_key=%s', (self.key,))
                    connection.execute('UPDATE social_deliveries SET next_attempt_at=0 WHERE subscription_id=%s', (active['id'],))
                await self.run_event()
            self.assertEqual(attempts, [1], 'The active guild must retain its finite retry limit')
            self.settings.set_module(2, 'youtube_updates', enabled=True)
            await self.run_event()
        self.assertEqual(self.port.calls, [(2, 12, True)], 'The paused guild must resume without redelivering sent receipts')
        self.assertEqual(self.repository.social_delivery(paused['id'], self.key)['state'], 'sent')
        self.assertEqual(attempts, [1])
        self.assertEqual(self.state()['status'], 'completed')

    async def test_expired_final_owner_does_not_exhaust_another_guilds_paused_intent(self):
        active, paused, sent = (self.subscription(guild) for guild in (1, 2, 3))
        self.event(attempts=8)
        self.repository.record_social_delivery(active['id'], self.key, 11, None, 'uncertain')
        self.repository.record_social_delivery(paused['id'], self.key, 12, None, 'uncertain')
        self.repository.record_social_delivery(sent['id'], self.key, 13, 903, 'sent')
        with transaction(self.url) as connection:
            connection.execute("UPDATE social_events SET status='processing',lease_owner='expired-worker',lease_token='expired-token',lease_until=%s WHERE event_key=%s",
                (int(time.time()) - 1, self.key))
            connection.execute('UPDATE social_deliveries SET attempts=8 WHERE subscription_id=%s', (active['id'],))
        self.settings.set_module(2, 'youtube_updates', enabled=False)
        paused_before = self.repository.social_delivery(paused['id'], self.key)
        for _ in range(10):
            await self.run_event()
        self.assertEqual(self.port.calls, [], 'An expired final attempt must not grant the active guild another delivery')
        self.assertEqual(self.repository.social_delivery(paused['id'], self.key), paused_before)
        self.settings.set_module(2, 'youtube_updates', enabled=True)
        await self.run_event()
        self.assertEqual(self.port.calls, [(2, 12, True)], 'Only the previously paused guild should resume')
        self.assertEqual(self.repository.social_delivery(paused['id'], self.key)['state'], 'sent')
        self.assertEqual(self.state()['status'], 'completed')

    async def test_dispatch_failure_before_attempt_reservation_has_a_finite_budget(self):
        sent, active, paused = (self.subscription(guild) for guild in (1, 2, 3))
        self.event(attempts=0)
        self.repository.record_social_delivery(sent['id'], self.key, 11, 901, 'sent')
        self.repository.record_social_delivery(active['id'], self.key, 12, None, 'pending')
        self.repository.record_social_delivery(paused['id'], self.key, 13, None, 'uncertain')
        with transaction(self.url) as connection:
            connection.execute('UPDATE social_deliveries SET attempts=1,dispatch_accounted_attempts=1 WHERE subscription_id=%s', (sent['id'],))
        self.settings.set_module(3, 'youtube_updates', enabled=False)
        original = self.repository.begin_social_delivery_attempt
        failures = []

        def fail_before_reservation(subscription_id, event_key):
            if subscription_id == active['id']:
                failures.append(subscription_id)
                raise RuntimeError('Dispatcher failed before reserving the delivery attempt')
            return original(subscription_id, event_key)

        from unittest.mock import patch
        with patch.object(self.repository, 'begin_social_delivery_attempt', side_effect=fail_before_reservation):
            for _ in range(32):
                await self.run_event()
                with transaction(self.url) as connection:
                    connection.execute('UPDATE social_events SET available_at=0 WHERE event_key=%s', (self.key,))
            self.assertLessEqual(len(failures), 8,
                'Past sent receipts must not repeatedly replenish the dispatcher retry budget')
            stopped_at = len(failures)
            for _ in range(8):
                self.assertEqual(await self.run_event(), 0)
            self.assertEqual(len(failures), stopped_at)
        self.assertEqual(self.port.calls, [])

    async def test_new_io_progress_grants_budget_once_then_dispatch_failures_stop(self):
        active, paused = self.subscription(1), self.subscription(2)
        self.event(attempts=7)
        self.repository.record_social_delivery(active['id'], self.key, 11, None, 'retry')
        self.repository.record_social_delivery(paused['id'], self.key, 12, None, 'uncertain')
        with transaction(self.url) as connection:
            connection.execute('UPDATE social_deliveries SET attempts=7 WHERE subscription_id=%s', (active['id'],))
        self.settings.set_module(2, 'youtube_updates', enabled=False)
        paused_before = self.repository.social_delivery(paused['id'], self.key)
        from unittest.mock import patch
        with patch.object(self.port, 'send', side_effect=DiscordFailure('Final I/O attempt failed', retry=True)):
            await self.run_event()
        exhausted = self.repository.social_delivery(active['id'], self.key)
        self.assertEqual(exhausted['state'], 'failed')
        self.assertEqual(exhausted['attempts'], 8)
        self.assertEqual(exhausted['dispatch_accounted_attempts'], 8)
        self.assertEqual(self.state()['attempts'], 0)
        self.assertEqual(self.repository.social_delivery(paused['id'], self.key), paused_before)
        self.settings.set_module(2, 'youtube_updates', enabled=True)
        failures = []

        def dispatcher_failure(*args):
            failures.append(1)
            raise RuntimeError('No new I/O progress')

        with patch.object(self.repository, 'begin_social_delivery_attempt', side_effect=dispatcher_failure):
            for _ in range(24):
                await self.run_event()
                with transaction(self.url) as connection:
                    connection.execute('UPDATE social_events SET available_at=0 WHERE event_key=%s', (self.key,))
            self.assertEqual(len(failures), 8)
            self.assertEqual(self.state()['status'], 'failed')
            self.assertEqual(await self.run_event(), 0)
        self.assertEqual(self.repository.social_delivery(active['id'], self.key)['dispatch_accounted_attempts'], 8)
        self.assertEqual(self.port.calls, [])
