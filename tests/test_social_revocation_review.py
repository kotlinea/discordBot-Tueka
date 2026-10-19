"""A revocation received during polling must survive the stale completion."""
import unittest
from unittest.mock import patch

from database.testing import temporary_database
from social.models import default_templates
from social.repository import SocialRepository


class SocialRevocationReviewTests(unittest.TestCase):
    def test_revocation_during_poll_preserves_subscription_reconciliation(self):
        with temporary_database() as database_url, patch('social.repository.time.time', return_value=2_000_000_000):
            repository = SocialRepository(database_url)
            subscription = repository.save_social_subscription_v2(
                1, 'twitch', 'creator', 10, ['live_start', 'live_end'], {},
                default_templates('twitch'))
            initial = repository.claim_social_targets('initial-worker')[0]
            self.assertTrue(repository.complete_social_target(
                initial['id'], initial['lease_owner'], status='active',
                cursor={'live': True, 'stream_id': 'A', 'eventsub_synced_at': 2_000_000_000},
                external_id='42', next_check_at=0))

            # Barrier 1: the poll retains this snapshot while its HTTP call runs.
            claimed = repository.claim_social_targets('poll-worker')[0]
            self.assertEqual(claimed['id'], subscription['target_id'])

            # Barrier 2: an authenticated revocation reaches the repository.
            self.assertEqual(repository.invalidate_social_target(
                'twitch', '42', 'authorization_revoked'), 1)
            invalidated = repository.social_target(claimed['id'])
            self.assertNotIn('eventsub_synced_at', invalidated['cursor'])
            self.assertEqual(invalidated['next_check_at'], 0)

            # Barrier 3: the in-flight poll returns its pre-revocation snapshot.
            repository.complete_social_target(
                claimed['id'], claimed['lease_owner'], status='active',
                cursor=claimed['cursor'], external_id='42', next_check_at=2_000_000_300,
                observed_wake_revision=claimed['wake_revision'])
            actual = repository.social_target(claimed['id'])
            with self.subTest(contract='revoked subscription marker remains cleared'):
                self.assertNotIn('eventsub_synced_at', actual['cursor'])
            with self.subTest(contract='subscription reconciliation remains immediately due'):
                self.assertEqual(actual['next_check_at'], 0)
