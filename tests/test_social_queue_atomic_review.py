"""Public queue contracts across budget reconciliation and lease boundaries."""
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event
from unittest.mock import patch

from database import transaction
from db_support import snapshot
from jobs import Outcome
import test_social_pause_review as pause_fixture


class SocialQueueAtomicReviewTests(unittest.IsolatedAsyncioTestCase):
    setUp = pause_fixture.SocialPauseReviewTests.setUp
    subscription = pause_fixture.SocialPauseReviewTests.subscription
    event = pause_fixture.SocialPauseReviewTests.event
    state = pause_fixture.SocialPauseReviewTests.state

    def recoverable_final(self, *, paused=None):
        active = self.subscription(1)
        if paused is None:
            paused = self.subscription(2)
        self.event(attempts=8)
        self.repository.record_social_delivery(active['id'], self.key, 11, None, 'uncertain')
        self.repository.record_social_delivery(paused['id'], self.key, 12, None, 'uncertain')
        self.settings.set_module(2, 'youtube_updates', enabled=False)
        with transaction(self.url) as c:
            c.execute('UPDATE social_deliveries SET attempts=8 WHERE subscription_id=%s', (active['id'],))
            c.execute('UPDATE social_events SET available_at=0 WHERE event_key=%s', (self.key,))
        return active, paused

    def test_old_paused_rows_do_not_hide_later_recoverable_final_event(self):
        paused = self.subscription(2)
        self.settings.set_module(2, 'youtube_updates', enabled=False)
        for number in range(100):
            external = f'older-paused-{number}'
            key = f'youtube:video:{external}'
            self.repository.enqueue_social_event_v2('youtube', external, 'creator', 'video', {})
            self.repository.record_social_delivery(paused['id'], key, 12, None, 'uncertain')
            with transaction(self.url) as c:
                c.execute('UPDATE social_events SET attempts=8,available_at=0 WHERE event_key=%s', (key,))
        self.recoverable_final(paused=paused)
        self.repository.event_jobs.claim('review')
        self.assertNotEqual(self.state()['status'], 'failed')
        self.settings.set_module(2, 'youtube_updates', enabled=True)
        self.assertIsNotNone(self.repository.event_jobs.claim('resume'))

    def test_row_skipped_during_reconciliation_can_resume_after_unlock(self):
        self.recoverable_final()
        blocker = transaction(self.url)
        holder = blocker.__enter__()
        holder.execute('SELECT id FROM social_events WHERE event_key=%s FOR UPDATE', (self.key,))
        released = False
        real_transaction = transaction

        @contextmanager
        def release_after_first_transaction(url):
            nonlocal released
            try:
                with real_transaction(url) as c:
                    yield c
            finally:
                if not released:
                    released = True
                    blocker.__exit__(None, None, None)

        try:
            with patch('social.repository.transaction', release_after_first_transaction), patch(
                    'jobs.repository.transaction', release_after_first_transaction):
                self.repository.event_jobs.claim('review')
            self.assertNotEqual(self.state()['status'], 'failed')
            self.settings.set_module(2, 'youtube_updates', enabled=True)
            self.assertIsNotNone(self.repository.event_jobs.claim('resume'))
        finally:
            if not released:
                blocker.__exit__(None, None, None)

    def test_invalid_claim_arguments_leave_all_database_state_unchanged(self):
        self.recoverable_final()
        for owner, seconds in (('', 60), ('review', 2)):
            with self.subTest(owner=owner, lease_seconds=seconds):
                before = snapshot(self.url)
                with self.assertRaises(ValueError):
                    self.repository.event_jobs.claim(owner, lease_seconds=seconds)
                self.assertEqual(snapshot(self.url), before)

    def test_final_finish_rolls_back_if_receipt_wait_crosses_lease_deadline(self):
        active, _ = self.recoverable_final()
        queue = self.repository.event_jobs
        now = [100]
        queue.clock = lambda: now[0]
        with transaction(self.url) as c:
            c.execute('UPDATE social_events SET attempts=7 WHERE event_key=%s', (self.key,))
        claim = queue.claim('review', lease_seconds=10)
        self.assertIsNotNone(claim)
        now[0] = 109
        before = snapshot(self.url)
        requested = Event()
        real_transaction = transaction

        class RequestedConnection:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, query, *args, **kwargs):
                if 'UPDATE social_deliveries' in str(query):
                    requested.set()
                return self.connection.execute(query, *args, **kwargs)

        @contextmanager
        def gated_transaction(url):
            with real_transaction(url) as c:
                yield RequestedConnection(c)

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction(self.url) as holder:
                holder.execute('SELECT id FROM social_deliveries WHERE subscription_id=%s FOR UPDATE', (active['id'],))
                with patch('social.repository.transaction', gated_transaction):
                    future = executor.submit(queue.finish, claim, Outcome('retry', retry=True))
                    self.assertTrue(requested.wait(5), 'receipt update was not reached')
                    now[0] = 111
            result = future.result(timeout=10)
        self.assertFalse(result)
        self.assertEqual(snapshot(self.url), before)
