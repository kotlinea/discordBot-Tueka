import random
import unittest
from giveaways.models import normalize, eligible, selection


class GiveawayModelTests(unittest.TestCase):
    def setUp(self):
        self.now = 500000
        self.values = {'title': 'Generated giveaway', 'channel_id': '20', 'ends_at': self.now + 60}

    def test_configuration_bounds_and_distinct_event_semantics(self):
        config = normalize(self.values, self.now)
        self.assertEqual(config['winner_count'], 1)
        event = normalize({**self.values, 'kind': 'event'}, self.now)
        self.assertEqual(event['winner_count'], 0)
        for change in ({'winner_count': True}, {'ends_at': self.now}, {'capacity': 1001}, {'retention_days': 0}, {'kind': 'other'}, {'required_role_ids': [10], 'denied_role_ids': [10]}, {'kind': 'event', 'winner_count': 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                normalize({**self.values, **change}, self.now)

    def test_eligibility_rejects_bot_wrong_guild_and_stale_membership(self):
        config = normalize({**self.values, 'required_role_ids': [10], 'denied_role_ids': [11], 'min_account_days': 2, 'min_member_days': 1}, self.now)
        member = {'id': 30, 'guild_id': 1, 'bot': False, 'role_ids': [10], 'created_at': 0, 'joined_at': 0}
        self.assertTrue(eligible(config, member, 1, self.now))
        for change in ({'guild_id': 2}, {'bot': True}, {'role_ids': []}, {'role_ids': [10, 11]}, {'joined_at': None}, {'created_at': self.now}):
            self.assertFalse(eligible(config, {**member, **change}, 1, self.now))

    def test_selection_is_unique_bounded_and_excludes_all_past_winners(self):
        pool, winners, digest = selection([30, 31, 30, 32], 20, previous=[30], rng=random.Random(7))
        self.assertEqual(pool, [31, 32])
        self.assertEqual(set(winners), {31, 32})
        self.assertEqual(len(digest), 64)
        self.assertEqual(selection([32, 31], 0)[2], digest)
        self.assertEqual(selection([], 3)[1], [])
