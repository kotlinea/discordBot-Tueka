import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from database import transaction
from db_support import prepare_database
from insights.models import DAY, day_key, membership_key
from insights.repository import InsightsRepository


class InsightsRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.url = prepare_database(Path(self.tmp.name) / 'insights', self.addCleanup)
        self.now = DAY * 20000 + 1000
        self.repo = InsightsRepository(self.url, clock=lambda: self.now)
        self.config = {'channel_ids': [20, 21], 'retention_days': 30, 'track_members': True}
        self.repo.settings.set_module(1, 'insights', enabled=True, settings=self.config)
        self.assertTrue(self.repo.claim(1, 'observer'))

    def today(self, guild=1):
        key = day_key(self.now)
        return self.repo.report(guild, key, key)['days'][0]

    def test_replayed_events_are_atomic_and_guild_channel_fenced(self):
        self.assertTrue(self.repo.event(1, 'observer', 'messages', '100', channel=20))
        self.assertFalse(self.repo.event(1, 'observer', 'messages', '100', channel=20))
        self.assertFalse(self.repo.event(1, 'other', 'messages', '101', channel=20))
        self.assertFalse(self.repo.event(2, 'observer', 'messages', '101', channel=20))
        self.assertFalse(self.repo.event(1, 'observer', 'messages', '102', channel=99))
        self.assertFalse(self.repo.event(1, 'observer', 'messages', '103', channel=20, occurred_at=self.now - 91))
        self.assertFalse(self.repo.event(1, 'observer', 'messages', '104', channel=20, occurred_at=self.now + 1))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.repo.event(1, 'observer', 'messages', '105', channel=20), range(2)))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(self.today()['messages'], 2)
        self.assertFalse(self.today(2)['observed'])

    def test_membership_rejoins_are_distinct_and_body_is_not_part_of_storage(self):
        for kind, joined_at in [('joins', 10), ('leaves', 10), ('joins', 11)]:
            key = membership_key('join' if kind == 'joins' else 'leave', 30, joined_at)
            self.assertTrue(self.repo.event(1, 'observer', kind, key))
            self.assertFalse(self.repo.event(1, 'observer', kind, key))
        self.assertEqual((self.today()['joins'], self.today()['leaves']), (2, 1))
        with transaction(self.url) as c:
            columns = [r['column_name'] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name LIKE 'insights_%'")]
        self.assertFalse({'content', 'body', 'attachment_url', 'username', 'display_name'} & set(columns))

    def test_voice_movement_exit_and_duplicate_event_do_not_double_count(self):
        self.repo.heartbeat(1, 'observer', {30: 20, 31: 20})
        self.now += 10
        self.repo.voice_change(1, 'observer', 30, 20, 21)
        self.now += 5
        self.repo.voice_change(1, 'observer', 30, 20, 21)
        self.now += 5
        self.repo.heartbeat(1, 'observer', {30: 21, 31: 20})
        self.assertEqual(self.today()['voice_seconds'], 40)
        self.assertEqual(self.today()['observed_seconds'], 20)
        self.now += 10
        self.repo.voice_change(1, 'observer', 30, 21, None)
        self.repo.voice_change(1, 'observer', 30, 21, None)
        self.repo.heartbeat(1, 'observer', {31: 20})
        self.assertEqual(self.today()['voice_seconds'], 60)
        self.assertEqual(self.today()['observed_seconds'], 30)

    def test_missing_snapshot_and_excessive_gap_do_not_invent_voice_time(self):
        self.repo.heartbeat(1, 'observer', {30: 20})
        self.now += 20
        self.repo.heartbeat(1, 'observer', {})
        self.assertEqual(self.today()['voice_seconds'], 0)
        self.repo.heartbeat(1, 'observer', {30: 20})
        self.now += 100
        self.assertFalse(self.repo.event(1, 'observer', 'joins', 'after-disconnect'))
        self.repo.heartbeat(1, 'observer', {30: 20})
        self.assertFalse(self.repo.event(1, 'observer', 'messages', 'from-gap', channel=20, occurred_at=self.now - 1))
        self.assertEqual(self.today()['voice_seconds'], 0)
        self.assertEqual(self.today()['observed_seconds'], 20)
        self.now += 10
        self.repo.heartbeat(1, 'observer', {30: 20})
        self.assertEqual(self.today()['voice_seconds'], 10)

    def test_delayed_messages_cannot_cross_collection_start_or_off_on_boundary(self):
        self.assertFalse(self.repo.event(1, 'observer', 'messages', 'before-start', channel=20, occurred_at=self.now - 1))
        self.now += 10
        self.repo.settings.set_module(1, 'insights', enabled=False, settings=self.config)
        self.now += 10
        self.repo.settings.set_module(1, 'insights', enabled=True, settings=self.config)
        self.assertFalse(self.repo.event(1, 'observer', 'messages', 'created-while-off', channel=20, occurred_at=self.now - 1))
        self.assertTrue(self.repo.event(1, 'observer', 'messages', 'new-observation', channel=20, occurred_at=self.now))
        self.assertEqual(self.today()['messages'], 1)

    def test_exclusive_observer_lease_and_restart_have_no_backfill(self):
        self.repo.heartbeat(1, 'observer', {30: 20})
        self.assertFalse(self.repo.claim(1, 'duplicate'))
        self.now += 91
        self.assertTrue(self.repo.claim(1, 'new-process'))
        self.assertFalse(self.repo.heartbeat(1, 'observer', {30: 20}))
        self.repo.release(1, 'observer')
        self.assertTrue(self.repo.heartbeat(1, 'new-process', {30: 20}))
        self.now += 10
        self.repo.heartbeat(1, 'new-process', {30: 20})
        self.assertEqual(self.today()['voice_seconds'], 10)
        self.repo.release(1, 'new-process')
        self.assertFalse(self.repo.report(1, day_key(self.now), day_key(self.now))['collecting'])

    def test_off_on_and_configuration_revision_reset_the_observation_boundary(self):
        self.repo.heartbeat(1, 'observer', {30: 20})
        self.now += 10
        self.repo.settings.set_module(1, 'insights', enabled=False, settings=self.config)
        self.assertFalse(self.repo.heartbeat(1, 'observer', {30: 20}))
        self.assertFalse(self.repo.event(1, 'observer', 'joins', 'off'))
        self.now += 10
        self.repo.settings.set_module(1, 'insights', enabled=True, settings=self.config)
        self.repo.heartbeat(1, 'observer', {30: 20})
        self.assertEqual(self.today()['voice_seconds'], 0)
        self.assertEqual(self.today()['observed_seconds'], 0)
        self.now += 10
        self.repo.heartbeat(1, 'observer', {30: 20})
        self.assertEqual(self.today()['voice_seconds'], 10)
        self.repo.settings.set_module(1, 'insights', enabled=True, settings={**self.config, 'channel_ids': [], 'track_members': False})
        self.now += 10
        self.repo.heartbeat(1, 'observer', {30: 20})
        self.assertFalse(self.repo.event(1, 'observer', 'joins', 'disabled-members'))
        self.assertEqual(self.today()['voice_seconds'], 10)

    def test_utc_midnight_has_no_unknown_day_as_zero(self):
        self.now = DAY * 20001 - 10
        self.repo.claim(1, 'observer')
        self.repo.heartbeat(1, 'observer', {30: 20})
        self.now += 20
        self.repo.heartbeat(1, 'observer', {30: 20})
        days = self.repo.report(1, day_key(self.now - DAY * 2), day_key(self.now))['days']
        self.assertFalse(days[0]['observed'])
        self.assertIsNone(days[0]['messages'])
        self.assertEqual([row['voice_seconds'] for row in days[1:]], [10, 10])
        self.assertEqual([row['observed_seconds'] for row in days[1:]], [10, 10])
        self.assertEqual(days[-1]['first_observed'], DAY * 20001)
        self.assertLess(days[-2]['last_observed'], DAY * 20001)

    def test_retention_shortening_purges_off_feature_and_internal_ids(self):
        self.repo.event(1, 'observer', 'messages', 'generated', channel=20)
        self.repo.heartbeat(1, 'observer', {30: 20})
        self.now += DAY
        self.repo.settings.set_module(1, 'insights', enabled=False, settings={**self.config, 'retention_days': 1})
        self.assertGreater(self.repo.purge()['removed'], 0)
        with transaction(self.url) as c:
            for table in ('insights_daily', 'insights_seen', 'insights_voice', 'insights_observers'):
                self.assertEqual(c.execute(f'SELECT count(*) AS n FROM {table}').fetchone()['n'], 0)
        self.assertFalse(self.today()['observed'])

    def test_clock_reversal_rolls_back_and_report_exposes_no_owner_or_member_id(self):
        self.repo.heartbeat(1, 'observer', {30: 20})
        self.now -= 1
        with self.assertRaises(ValueError):
            self.repo.heartbeat(1, 'observer', {30: 20})
        self.now += 11
        self.repo.heartbeat(1, 'observer', {30: 20})
        report = self.repo.report(1, day_key(self.now), day_key(self.now))
        self.assertEqual(report['days'][0]['voice_seconds'], 10)
        self.assertNotIn('owner', report)
        self.assertNotIn('user_id', str(report))
