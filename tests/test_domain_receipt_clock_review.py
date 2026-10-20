"""Domain receipt commits must evaluate lease time after real row-lock waits."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
import time
import unittest

from database import connect, transaction
from database.testing import temporary_database
from jobs import LostLease, Outcome
from jobs.repository import ResourceLeaseRepository
import suggestions.repository as suggestions
import starboard.repository as starboard
import giveaways.repository as giveaways
import scheduling.repository as scheduling
import moderation.repository as moderation


class DomainReceiptClockReviewTests(unittest.TestCase):
    def wait_for_lock(self, observer, pid):
        deadline = time.monotonic() + 5
        tick = Event()
        while time.monotonic() < deadline:
            row = observer.execute(
                "SELECT wait_event_type='Lock' AS waiting FROM pg_stat_activity WHERE pid=%s",
                (pid,)).fetchone()
            if row and row['waiting']:
                return
            tick.wait(.01)
        self.fail('Expected outbox row-lock wait was not observed')

    def case(self, domain, release_time, *, block_parent=False):
        with temporary_database() as url:
            clock = [100]
            if domain.startswith('suggestion'):
                module = suggestions
                repo = suggestions.SuggestionRepository(url)
                repo.settings.set_module(1, 'suggestions', enabled=True)
                item = repo.create(1, 10, 20, {'idea': 'Clock probe'})
                claim = repo.outbox_jobs.claim('clock-owner')
                table = 'suggestion_outbox'
                if domain == 'suggestion_failed':
                    operation = lambda: repo.delivery_state(claim.payload, started=False, failed='definitive rejection')
                    column = 'status'
                elif domain == 'suggestion_state':
                    operation = lambda: repo.delivery_state(claim.payload, started=True)
                    column, parent, item = 'delivery_started', 'suggestion_outbox', {'id': claim.id}
                elif domain == 'suggestion_sync':
                    operation = lambda: repo.queue_sync(1, item['id'], job=claim.payload)
                    column = 'message_id'
                elif domain == 'suggestion_publish':
                    operation = lambda: repo.publication_delivered(claim.payload, 900)
                    column = 'message_id'
                else:
                    repo.publication_delivered(claim.payload, 800, discussion=True)
                    self.assertTrue(repo.outbox_jobs.finish(claim, Outcome()))
                    sync = repo.outbox_jobs.claim('setup-sync')
                    self.assertEqual(sync.payload['action'], 'sync')
                    self.assertTrue(repo.outbox_jobs.finish(sync, Outcome()))
                    claim = repo.outbox_jobs.claim('clock-owner')
                    self.assertEqual(claim.payload['action'], 'discussion')
                    operation = lambda: repo.discussion_delivered(claim.payload, 900)
                    column = 'discussion_thread_id'
                if domain != 'suggestion_state':
                    parent = 'suggestions'
            elif domain == 'starboard':
                module = starboard
                repo = starboard.StarboardRepository(url, clock=lambda: clock[0])
                repo.settings.set_module(1, 'starboard', enabled=True)
                board = repo.save_board(1, 30, {'name': 'Clock', 'enabled': True,
                    'target_channel_id': 20, 'source_channel_ids': [10], 'threshold': 2})
                item = repo.observe(1, board['id'], 1, {'guild_id': 1, 'channel_id': 10,
                    'message_id': 100, 'author_id': 40, 'author_bot': False, 'content': 'Clock'}, 2)
                claim = repo.jobs.claim('clock-owner')
                publication, _ = repo.publication_begin(claim.payload, 20)
                operation = lambda: repo.publication_receipt(claim.payload, publication['id'], 900)
                table, parent, column = 'starboard_outbox', 'starboard_publications', 'message_id'
                item = publication
            elif domain == 'giveaway':
                module = giveaways
                repo = giveaways.GiveawayRepository(url, clock=lambda: clock[0])
                repo.settings.set_module(1, 'giveaways', enabled=True)
                item = repo.create(1, 10, {'title': 'Clock', 'channel_id': 20, 'ends_at': 1000}, 'clock')
                item = repo.launch(1, item['id'], 10, item['revision'])
                claim = repo.jobs.claim('clock-owner')
                operation = lambda: repo.publication_receipt(claim.payload, 900)
                table, parent, column = 'giveaway_outbox', 'giveaways', 'message_id'
            elif domain.startswith('schedule'):
                module = scheduling
                repo = scheduling.ScheduleRepository(url, clock=lambda: clock[0])
                repo.settings.set_module(1, 'scheduled_messages', enabled=True)
                repo.create(1, 20, {'kind': 'message', 'body': 'Clock', 'channel_id': 10,
                    'run_at': 130}, 'clock')
                clock[0] = 130
                self.assertEqual(repo.enqueue_due(), 1)
                claim = repo.jobs.claim('clock-owner')
                table, parent = 'scheduled_post_outbox', 'scheduled_post_outbox'
                item = {'id': claim.id}
                if domain == 'schedule_state':
                    column = 'discord_receipt_id'
                    operation = lambda: repo.delivery_state(claim.payload, receipt=900)
                else:
                    column = 'delivery_started'
                    operation = lambda: repo.start_delivery(claim.payload)
            else:
                module = moderation
                repo = moderation.ModerationRepository(url)
                identifier = repo.schedule_moderation_action(1, 20, 'unban', 1, 'Clock', None)
                claim = repo.schedule_jobs.claim('clock-owner')
                lease = ResourceLeaseRepository(url, 'clock-probe', identifier, seconds=100,
                    clock=lambda: 100)
                lease.acquire()
                operation = lambda: repo.expiring_tempban(claim.payload, lease=lease)
                table = parent = 'scheduled_moderation_actions'
                column, item = 'completed_at', {'id': identifier}

            with transaction(url) as connection:
                connection.execute(f'UPDATE {table} SET lease_until=110 WHERE id=%s', (claim.id,))
            entered, backend = Event(), []

            @contextmanager
            def tracked_transaction(database_url):
                with transaction(database_url) as connection:
                    backend.append(connection.info.backend_pid)
                    entered.set()
                    yield connection

            clock[0] = 109
            with connect(url, autocommit=True) as observer, connect(url, autocommit=True) as blocker:
                with ThreadPoolExecutor(max_workers=1) as executor, patch.object(
                    module, 'transaction', tracked_transaction
                ), patch.object(module, 'time', SimpleNamespace(time=lambda: clock[0])):
                    with blocker.transaction():
                        blocked_table = parent if block_parent else table
                        blocked_id = item['id'] if block_parent else claim.id
                        blocker.execute(f'SELECT id FROM {blocked_table} WHERE id=%s FOR UPDATE', (blocked_id,))
                        future = executor.submit(operation)
                        self.assertTrue(entered.wait(5))
                        self.wait_for_lock(observer, backend[0])
                        clock[0] = release_time
                    if release_time < 110:
                        actual = future.result(timeout=5)
                        if domain == 'schedule_state':
                            self.assertTrue(actual)
                    else:
                        if domain == 'schedule_state':
                            self.assertFalse(future.result(timeout=5))
                        else:
                            with self.assertRaises(LostLease):
                                future.result(timeout=5)
                row = observer.execute(f'SELECT {column} FROM {parent} WHERE id=%s', (item['id'],)).fetchone()
                if domain == 'suggestion_failed':
                    self.assertEqual(row[column], 'delivery_failed' if release_time < 110 else 'pending')
                elif domain in ('suggestion_state', 'schedule_start'):
                    self.assertEqual(row[column], int(release_time < 110))
                elif domain in ('suggestion_sync', 'moderation'):
                    self.assertIsNone(row[column])
                else:
                    self.assertEqual(row[column], 900 if release_time < 110 else None)
                if domain == 'suggestion_sync':
                    count = observer.execute("SELECT count(*) AS n FROM suggestion_outbox WHERE action='sync'").fetchone()['n']
                    self.assertEqual(count, int(release_time < 110))

    def test_domain_receipt_commit_checks_time_after_outbox_lock(self):
        for domain in ('suggestion_publish', 'suggestion_discussion', 'starboard', 'giveaway',
                       'suggestion_state', 'suggestion_sync', 'schedule_start', 'schedule_state', 'moderation'):
            for release_time in (109, 110, 111):
                with self.subTest(domain=domain, release_time=release_time):
                    self.case(domain, release_time)

    def test_suggestion_receipt_checks_time_after_parent_lock(self):
        for domain in ('suggestion_publish', 'suggestion_discussion', 'suggestion_failed', 'suggestion_sync'):
            for release_time in (109, 110, 111):
                with self.subTest(domain=domain, release_time=release_time):
                    self.case(domain, release_time, block_parent=True)

    def test_suggestion_publication_checks_time_after_merged_child_lock(self):
        for release_time in (109, 110, 111):
            with self.subTest(release_time=release_time), temporary_database() as url:
                repo = suggestions.SuggestionRepository(url)
                repo.settings.set_module(1, 'suggestions', enabled=True)
                root = repo.create(1, 10, 20, {'idea': 'Canonical publication'})
                child = repo.create(1, 10, 21, {'idea': 'Duplicate publication'})
                repo.merge(1, child['id'], root['id'], 40, 'Duplicate idea',
                           child['revision'], root['revision'])
                claim = repo.outbox_jobs.claim('clock-owner')
                self.assertEqual(claim.payload['suggestion_id'], root['id'])
                self.assertEqual(claim.payload['action'], 'publish')
                with transaction(url) as connection:
                    connection.execute('UPDATE suggestion_outbox SET lease_until=110 WHERE id=%s',
                                       (claim.id,))
                    before = connection.execute(
                        "SELECT count(*) AS n FROM suggestion_outbox WHERE action='sync'"
                    ).fetchone()['n']
                clock, backend, entered = [109], [], Event()

                @contextmanager
                def tracked_transaction(database_url):
                    with transaction(database_url) as connection:
                        backend.append(connection.info.backend_pid)
                        entered.set()
                        yield connection

                with connect(url, autocommit=True) as observer, connect(url, autocommit=True) as blocker:
                    with ThreadPoolExecutor(max_workers=1) as executor, patch.object(
                        suggestions, 'transaction', tracked_transaction
                    ), patch.object(suggestions, 'time', SimpleNamespace(time=lambda: clock[0])):
                        with blocker.transaction():
                            blocker.execute('SELECT id FROM suggestions WHERE id=%s FOR UPDATE',
                                            (child['id'],))
                            future = executor.submit(repo.publication_delivered, claim.payload, 900)
                            self.assertTrue(entered.wait(5))
                            self.wait_for_lock(observer, backend[0])
                            clock[0] = release_time
                        if release_time < 110:
                            future.result(timeout=5)
                        else:
                            with self.assertRaises(LostLease):
                                future.result(timeout=5)
                    receipt = observer.execute('SELECT message_id FROM suggestions WHERE id=%s',
                                               (root['id'],)).fetchone()['message_id']
                    self.assertEqual(receipt, 900 if release_time < 110 else None)
                    after = observer.execute(
                        "SELECT count(*) AS n FROM suggestion_outbox WHERE action='sync'"
                    ).fetchone()['n']
                    self.assertEqual(after, before + (2 if release_time < 110 else 0))
