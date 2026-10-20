"""Target lease decisions use time after real pool/row/advisory waits."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

from database import connect, lock_resource
from database.connections import pool
from database.testing import temporary_database
import social.repository as social_repository


class SocialTargetClockReviewTests(unittest.TestCase):
    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        tick = Event()
        while time.monotonic() < deadline:
            if predicate():
                return
            tick.wait(.01)
        self.fail('Database wait was not observed before synchronization deadline')

    def seed(self, repository, *, orphan=False):
        subscription = repository.save_social_subscription_v2(
            1, 'twitch', 'clock-probe', 2, ['live_start'], {}, {})
        if orphan:
            repository.delete_social_subscription(1, subscription['id'])
        with patch.object(social_repository, 'time', SimpleNamespace(time=lambda: 100)):
            return repository.claim_social_targets('clock-owner', lease_seconds=10)[0]

    def locked_case(self, operation, barrier, release_time):
        with temporary_database() as url:
            repository = social_repository.SocialRepository(url)
            target = self.seed(repository, orphan=operation == 'delete')
            clock = [109]
            backend = []
            entered = Event()
            original = repository._connection

            @contextmanager
            def tracked_connection():
                with original() as connection:
                    backend.append(connection.info.backend_pid)
                    entered.set()
                    yield connection

            repository._connection = tracked_connection
            with connect(url, autocommit=True) as observer, connect(url, autocommit=True) as blocker:
                with ThreadPoolExecutor(max_workers=1) as executor, patch.object(
                    social_repository, 'time', SimpleNamespace(time=lambda: clock[0])
                ):
                    with blocker.transaction():
                        if barrier == 'advisory':
                            lock_resource(blocker, 'social-provider-targets', 'twitch')
                        else:
                            blocker.execute('SELECT id FROM social_targets WHERE id=%s FOR UPDATE', (target['id'],))
                        if operation == 'complete':
                            future = executor.submit(
                                repository.complete_social_target, target['id'], target['lease_owner'],
                                status='active', cursor={'clock_probe': True}, next_check_at=1000,
                                events=[{'external_id': 'clock-event', 'account_id': 'clock-probe',
                                         'event_type': 'live_start', 'payload': {}}])
                        else:
                            future = executor.submit(repository.delete_social_target, target['id'], target['lease_owner'])
                        self.assertTrue(entered.wait(5))
                        self.wait_for(lambda: observer.execute(
                            "SELECT wait_event_type='Lock' AS waiting FROM pg_stat_activity WHERE pid=%s",
                            (backend[0],)).fetchone()['waiting'])
                        clock[0] = release_time
                    actual = future.result(timeout=5)
                row = repository.social_target(target['id'])
                events = observer.execute('SELECT COUNT(*) AS n FROM social_events').fetchone()['n']
                valid = release_time < target['lease_until']
                self.assertEqual(actual, valid)
                if operation == 'complete':
                    self.assertEqual(events, int(valid))
                    self.assertEqual(row['cursor'], {'clock_probe': True} if valid else target['cursor'])
                    self.assertEqual(row['lease_owner'], None if valid else target['lease_owner'])
                else:
                    self.assertEqual(row is None, valid)

    def test_completion_checks_expiry_after_provider_and_row_lock(self):
        for barrier in ['advisory', 'row']:
            for release_time in [109, 110, 111]:
                with self.subTest(barrier=barrier, release_time=release_time):
                    self.locked_case('complete', barrier, release_time)

    def test_cleanup_checks_expiry_after_row_lock(self):
        for release_time in [109, 110, 111]:
            with self.subTest(release_time=release_time):
                self.locked_case('delete', 'row', release_time)

    def pool_case(self, operation):
        with temporary_database() as url:
            repository = social_repository.SocialRepository(url)
            target = self.seed(repository)
            clock = [109 if operation == 'complete' else 100]
            connections = pool(url)
            with ThreadPoolExecutor(max_workers=1) as executor, patch.object(
                social_repository, 'time', SimpleNamespace(time=lambda: clock[0])
            ):
                with connections.connection(), connections.connection(), connections.connection(), connections.connection():
                    if operation == 'complete':
                        future = executor.submit(repository.complete_social_target, target['id'], target['lease_owner'],
                                                 status='active', cursor={'clock_probe': True}, next_check_at=1000)
                    else:
                        with connect(url, autocommit=True) as connection:
                            connection.execute('UPDATE social_targets SET lease_owner=NULL,lease_until=NULL WHERE id=%s',
                                               (target['id'],))
                        future = executor.submit(repository.claim_social_targets, 'pool-worker', lease_seconds=10)
                    self.wait_for(lambda: connections.get_stats().get('requests_waiting', 0) == 1)
                    clock[0] = 111
                result = future.result(timeout=5)
            if operation == 'complete':
                self.assertFalse(result)
                self.assertEqual(repository.social_target(target['id'])['cursor'], target['cursor'])
            else:
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]['lease_until'], 121)
                self.assertNotEqual(result[0]['lease_owner'], target['lease_owner'])

    def test_completion_checks_expiry_after_pool_acquisition(self):
        self.pool_case('complete')

    def test_claim_duration_starts_after_pool_acquisition(self):
        self.pool_case('claim')

    def test_expired_lease_is_reclaimable_at_exact_expiry(self):
        for now in [109, 110, 111]:
            with self.subTest(now=now), temporary_database() as url:
                repository = social_repository.SocialRepository(url)
                target = self.seed(repository)
                with patch.object(social_repository, 'time', SimpleNamespace(time=lambda: now)):
                    completed = repository.complete_social_target(target['id'], target['lease_owner'],
                                                                  status='active', cursor={}, next_check_at=1000)
                    reclaimed = repository.claim_social_targets('replacement') if not completed else []
                self.assertEqual(completed, now < 110)
                self.assertEqual(bool(reclaimed), now >= 110)


if __name__ == '__main__':
    unittest.main()
