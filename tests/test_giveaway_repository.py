import json
import random
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from db_support import prepare_database
from database import transaction
from giveaways.repository import GiveawayRepository
from jobs import Outcome, LostLease


class GiveawayRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.url = prepare_database(Path(self.tmp.name) / 'giveaway', self.addCleanup)
        self.now = 500000
        self.repo = GiveawayRepository(self.url, clock=lambda: self.now)
        self.repo.settings.set_module(1, 'giveaways', enabled=True)
        self.values = {'title': 'Generated giveaway', 'channel_id': 20, 'ends_at': self.now + 60, 'retention_days': 1}
        self.item = self.repo.create(1, 10, self.values, 'generated')

    def launch(self):
        self.item = self.repo.launch(1, self.item['id'], 10, self.item['revision'])
        claim = self.repo.jobs.claim('publisher')
        self.assertEqual(self.repo.publication_begin(claim.payload), 'send')
        self.repo.publication_receipt(claim.payload, 100)
        self.assertTrue(self.repo.jobs.finish(claim, Outcome()))

    def join(self, user, interaction=None):
        return self.repo.enter(1, self.item['id'], user, 100, interaction or user * 10, join=True)

    def draw(self):
        claim = self.repo.draw_jobs.claim('draw')
        plan = self.repo.draw_plan(claim.payload)
        result = self.repo.complete_draw(claim.payload, plan['campaign']['revision'], plan['entrants'], rng=random.Random(3))
        self.repo.draw_jobs.finish(claim, Outcome())
        return result

    def test_parallel_creates_are_actor_bound_and_idempotent(self):
        with ThreadPoolExecutor(4) as pool:
            ids = list(pool.map(lambda _: self.repo.create(1, 10, self.values, 'same')['id'], range(4)))
        self.assertEqual(len(set(ids)), 1)
        with self.assertRaises(RuntimeError):
            self.repo.create(1, 11, self.values, 'same')

    def test_deadline_receipt_guild_and_immutable_config_guards(self):
        with self.assertRaises(RuntimeError):
            self.join(30)
        self.launch()
        with self.assertRaises(LookupError):
            self.repo.item(2, self.item['id'])
        with self.assertRaises(RuntimeError):
            self.repo.enter(1, self.item['id'], 30, 999, 300, join=True)
        self.assertTrue(self.join(30))
        self.assertFalse(self.join(30))
        row = self.repo.item(1, self.item['id'])
        with self.assertRaises(RuntimeError):
            self.repo.edit(1, row['id'], 10, self.values, row['revision'])
        self.now += 60
        with self.assertRaises(RuntimeError):
            self.join(31)

    def test_parallel_join_respects_capacity_and_releases_slot_on_leave(self):
        self.item = self.repo.edit(1, self.item['id'], 10, {**self.values, 'capacity': 1}, self.item['revision'])
        self.launch()
        def attempt(user):
            try:
                return self.join(user)
            except ValueError:
                return False
        with ThreadPoolExecutor(4) as pool:
            self.assertEqual(sum(pool.map(attempt, (30, 31, 32, 33))), 1)
        winner = next(e['user_id'] for e in self.repo.history(1, self.item['id'])['entries'] if e['active'])
        self.repo.enter(1, self.item['id'], winner, 100, 999, join=False)
        self.assertTrue(self.join(40))

    def test_duplicate_interaction_cannot_reverse_later_leave(self):
        self.launch()
        self.join(30, 300)
        self.repo.enter(1, self.item['id'], 30, 100, 301, join=False)
        self.assertFalse(self.join(30, 300))
        self.assertEqual(self.repo.history(1, self.item['id'])['entries'][0]['active'], 0)
        with self.assertRaises(RuntimeError):
            self.repo.enter(1, self.item['id'], 31, 100, 300, join=True)

    def test_draw_replay_and_reroll_preserve_prior_results(self):
        self.launch()
        for user in (30, 31, 32):
            self.join(user)
        self.assertIsNone(self.repo.draw_jobs.claim('too-early'))
        self.now += 60
        first = self.draw()
        current = self.repo.item(1, self.item['id'])
        self.assertEqual(current['status'], 'closed')
        self.repo.reroll(1, current['id'], 11, current['revision'], 'Generated reroll proof')
        second = self.draw()
        self.assertFalse(set(json.loads(first['winners_json'])) & set(json.loads(second['winners_json'])))
        self.assertEqual(len(self.repo.history(1, current['id'])['draws']), 2)

    def test_crash_after_commit_recovers_same_draw_without_sampling_again(self):
        self.launch()
        self.join(30)
        self.now += 60
        old = self.repo.draw_jobs.claim('old', lease_seconds=3)
        plan = self.repo.draw_plan(old.payload)
        result = self.repo.complete_draw(old.payload, plan['campaign']['revision'], [30])
        self.now += 4
        claim = self.repo.draw_jobs.claim('new')
        self.assertEqual(self.repo.draw_plan(claim.payload)['existing']['id'], result['id'])
        with self.assertRaises(LostLease):
            self.repo.complete_draw(old.payload, plan['campaign']['revision'], [30])
        self.assertEqual(self.repo.complete_draw(claim.payload, 0, [])['id'], result['id'])

    def test_cancel_fences_inflight_draw_and_keeps_audit(self):
        self.launch()
        self.join(30)
        self.now += 60
        claim = self.repo.draw_jobs.claim('draw')
        plan = self.repo.draw_plan(claim.payload)
        self.repo.cancel(1, self.item['id'], 11, plan['campaign']['revision'], 'Generated cancel')
        with self.assertRaises(LostLease):
            self.repo.complete_draw(claim.payload, plan['campaign']['revision'], [30])
        self.assertEqual(self.repo.history(1, self.item['id'])['draws'], [])

    def test_final_attempt_crash_can_acknowledge_recorded_draw_without_reroll(self):
        self.launch()
        self.join(30)
        self.now += 60
        with transaction(self.url) as c:
            c.execute('UPDATE giveaway_draw_jobs SET attempts=7 WHERE campaign_id=%s', (self.item['id'],))
        claim = self.repo.draw_jobs.claim('final-attempt', lease_seconds=3)
        plan = self.repo.draw_plan(claim.payload)
        result = self.repo.complete_draw(claim.payload, plan['campaign']['revision'], [30])
        self.now += 4
        self.assertIsNone(self.repo.draw_jobs.claim('reaper'))
        row = self.repo.item(1, self.item['id'])
        self.repo.retry(1, row['id'], 10, row['revision'], claim.id, draw=True)
        recovered = self.repo.draw_jobs.claim('acknowledger')
        self.assertEqual(self.repo.draw_plan(recovered.payload)['existing']['id'], result['id'])
        self.assertTrue(self.repo.draw_jobs.finish(recovered, Outcome()))
        self.assertEqual(len(self.repo.history(1, row['id'])['draws']), 1)

    def test_off_pauses_jobs_and_retention_cascades_only_expired_campaign(self):
        self.launch()
        self.join(30)
        self.repo.settings.set_module(1, 'giveaways', enabled=False)
        self.now += 60
        self.assertIsNone(self.repo.draw_jobs.claim('paused'))
        with self.assertRaises(PermissionError):
            self.join(31)
        self.now += 86401
        self.assertEqual(self.repo.purge_expired(), 1)
        with transaction(self.url) as c:
            self.assertEqual(c.execute('SELECT count(*) AS n FROM giveaway_entries').fetchone()['n'], 0)
            self.assertEqual(c.execute('SELECT count(*) AS n FROM giveaway_draw_jobs').fetchone()['n'], 0)

    def test_event_capacity_closes_without_random_winners_and_cannot_reroll(self):
        self.item = self.repo.edit(1, self.item['id'], 10, {**self.values, 'kind': 'event', 'winner_count': 0}, self.item['revision'])
        self.launch()
        self.join(30)
        row = self.repo.item(1, self.item['id'])
        self.repo.close(1, row['id'], 10, row['revision'], 'Registration complete')
        result = self.draw()
        self.assertEqual(json.loads(result['candidates_json']), [30])
        self.assertEqual(json.loads(result['winners_json']), [])
        row = self.repo.item(1, row['id'])
        with self.assertRaises(RuntimeError):
            self.repo.reroll(1, row['id'], 10, row['revision'], 'Invalid event reroll')
