import unittest
from datetime import datetime, timezone

from insights.models import DAY, MAX_GAP, day_key, membership_key, normalize, period, segments


class InsightsModelTests(unittest.TestCase):
    def test_explicit_channels_and_strict_collection_settings(self):
        self.assertEqual(normalize({}), {'channel_ids': [], 'retention_days': 30, 'track_members': True})
        self.assertEqual(normalize({'channel_ids': ['20', 10, 20]})['channel_ids'], [10, 20])
        for values in ({'channel_ids': '20'}, {'channel_ids': [True]}, {'channel_ids': ['２０']},
                       {'channel_ids': list(range(1, 27))}, {'channel_ids': [2**63]},
                       {'retention_days': True}, {'retention_days': 0}, {'retention_days': 366},
                       {'track_members': 1}, {'message_content': True}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                normalize(values)

    def test_utc_date_range_is_inclusive_bounded_and_inside_retention(self):
        now = int(datetime(2026, 10, 18, 1, tzinfo=timezone.utc).timestamp())
        self.assertEqual(period('2026-10-17', '2026-10-18', now, 2), ['2026-10-17', '2026-10-18'])
        self.assertEqual(len(period('2026-07-21', '2026-10-18', now, 365)), 90)
        for start, end, retention in [('2026-07-20', '2026-10-18', 365), ('2026-10-17', '2026-10-18', 1),
                                      ('2026-10-19', '2026-10-19', 30), ('2026-10-18', '2026-10-17', 30),
                                      ('2026-02-30', '2026-10-18', 365), ('2026-1-01', '2026-10-18', 365)]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                period(start, end, now, retention)

    def test_voice_and_coverage_split_utc_midnight_without_losing_seconds(self):
        midnight = int(datetime(2026, 10, 18, tzinfo=timezone.utc).timestamp())
        self.assertEqual(segments(midnight - 20, midnight + 30), [('2026-10-17', 20), ('2026-10-18', 30)])
        self.assertEqual(sum(n for _, n in segments(midnight - 20, midnight + 30)), 50)
        self.assertEqual(segments(midnight, midnight), [])
        self.assertEqual(segments(midnight, midnight + MAX_GAP), [('2026-10-18', MAX_GAP)])
        self.assertEqual(segments(midnight, midnight + MAX_GAP + 1), [])
        self.assertEqual(segments(midnight, midnight + DAY), [])
        for start, end in [(10, 9), (-1, 5), (True, 10), (10, 10.5)]:
            with self.assertRaises(ValueError):
                segments(start, end)
        self.assertEqual(day_key(0), '1970-01-01')

    def test_membership_replay_key_distinguishes_rejoin_and_action(self):
        key = membership_key('join', 30, 1000001)
        self.assertEqual(key, membership_key('join', '30', 1000001))
        self.assertEqual(len(key), 64)
        self.assertNotEqual(key, membership_key('leave', 30, 1000001))
        self.assertNotEqual(key, membership_key('join', 30, 1000002))
        self.assertNotEqual(key, membership_key('join', 31, 1000001))
        for values in [('unknown', 30, 1), ('join', True, 1), ('join', 30, None), ('leave', 30, 1.1)]:
            with self.assertRaises(ValueError):
                membership_key(*values)
