"""Real PostgreSQL migration, transaction, and isolation checks."""
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from psycopg import IntegrityError

from database import SchemaNotReady, connect, require_current, transaction
from database.migrations import MIGRATIONS, apply, load
from database.testing import temporary_database


class PostgresTests(unittest.TestCase):
    def setUp(self):
        self.context = temporary_database(migrate=False)
        self.url = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)

    def test_empty_schema_gate_initialization_and_idempotency(self):
        with self.assertRaises(SchemaNotReady):
            require_current(self.url)
        self.assertEqual(apply(self.url)['applied'], [row[1] for row in load()])
        require_current(self.url)
        self.assertEqual(apply(self.url)['applied'], [])
        with transaction(self.url) as c:
            self.assertEqual(c.execute('SELECT count(*) count FROM information_schema.tables WHERE table_schema=current_schema()').fetchone()['count'], 79)

    def test_transaction_and_migration_failures_roll_back(self):
        apply(self.url)
        with self.assertRaises(IntegrityError):
            with transaction(self.url) as c:
                c.execute("INSERT INTO app_metadata VALUES('same','first')")
                c.execute("INSERT INTO app_metadata VALUES('same','duplicate')")
        with transaction(self.url) as c:
            self.assertIsNone(c.execute('SELECT * FROM app_metadata').fetchone())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for migration in MIGRATIONS.glob('*.sql'):
                (root / migration.name).write_bytes(migration.read_bytes())
            (root / f'{len(load()) + 1:04d}_failure.sql').write_text("INSERT INTO app_metadata VALUES('partial','discard'); INSERT INTO app_metadata VALUES('partial','fail');")
            with self.assertRaises(IntegrityError):
                apply(self.url, root)
        require_current(self.url)
        with transaction(self.url) as c:
            self.assertIsNone(c.execute('SELECT * FROM app_metadata').fetchone())

    def test_changed_history_is_rejected_without_repair(self):
        apply(self.url)
        with transaction(self.url) as c:
            c.execute("UPDATE schema_migrations SET checksum='changed'")
        with self.assertRaises(ValueError):
            apply(self.url)
        with self.assertRaises(SchemaNotReady):
            require_current(self.url)

    def test_competing_migration_is_rejected(self):
        with connect(self.url) as owner:
            owner.execute("SELECT pg_advisory_xact_lock(hashtextextended(current_database() || ':' || current_schema() || ':tueka-migrate', 0))")
            with ThreadPoolExecutor(max_workers=1) as executor:
                with self.assertRaisesRegex(RuntimeError, 'Another migration'):
                    executor.submit(apply, self.url).result(timeout=10)

    def test_schema_isolation_and_large_ids(self):
        apply(self.url)
        with transaction(self.url) as c:
            c.execute('INSERT INTO guild_users(guild_id,user_id,xp) VALUES(%s,%s,%s)', (1234567890123456789, 1234567890123456790, 1))
        with temporary_database() as other:
            with transaction(other) as c:
                self.assertIsNone(c.execute('SELECT * FROM guild_users').fetchone())
        with transaction(self.url) as c:
            self.assertEqual(c.execute('SELECT guild_id FROM guild_users').fetchone()['guild_id'], 1234567890123456789)

    def test_preferences_and_module_revision_have_one_concurrent_winner(self):
        from dashboard.repository import DashboardRepository
        from guild_settings import GuildSettingsRepository
        apply(self.url)
        dashboard = DashboardRepository(self.url)
        modules = GuildSettingsRepository(self.url)

        def update(kind):
            try:
                if kind == 'preferences':
                    return dashboard.set_dashboard_preferences(1, locale='en', appearance='community',
                        color_scheme='dark', navigation_collapsed=True, expected_revision=0)['revision']
                return modules.set_module(1, 'welcome', enabled=True, settings={}, expected_revision=0)['revision']
            except RuntimeError as exc:
                self.assertEqual(str(exc), 'revision_conflict')
                return 'conflict'

        for kind in ('preferences', 'module'):
            with ThreadPoolExecutor(max_workers=4) as executor:
                values = list(executor.map(update, [kind] * 4))
            self.assertEqual(values.count(1), 1)
            self.assertEqual(values.count('conflict'), 3)

    def test_community_upserts_and_poll_closure(self):
        import time
        from community import CommunityRepository
        from engagement import EngagementRepository
        apply(self.url)
        community = CommunityRepository(self.url)
        community.add_temporary_voice_channel(10, 1, 20)
        community.add_temporary_voice_channel(10, 1, 21)
        self.assertEqual(community.temporary_voice_channel(10)['owner_id'], 21)
        community.add_xp(1, 20, 5)
        self.assertEqual(community.add_xp(1, 20, 7)['xp'], 12)
        community.add_voice_xp(1, 20, 3)
        self.assertEqual(community.add_voice_xp(1, 20, 2)['xp'], 5)
        engagement = EngagementRepository(self.url)
        engagement.create_poll(100, 1, 10, 20, 'Choice', ['A', 'B'], None, int(time.time()) + 100)
        self.assertEqual(engagement.cast_poll_vote(100, 20, 0), [1, 0])
        self.assertEqual(engagement.cast_poll_vote(100, 20, 1), [0, 1])
        with transaction(self.url) as c:
            c.execute('UPDATE polls SET closes_at=0')
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: engagement.close_expired_polls(), range(2)))
        self.assertEqual(sum(map(len, results)), 1)

    def test_queue_concurrent_claim_and_expired_owner(self):
        from jobs import QueueRepository, QueueSpec
        from jobs.models import Outcome
        apply(self.url)
        with transaction(self.url) as c:
            c.execute("INSERT INTO social_events(provider,event_key,account_id,payload_json,received_at) VALUES('x','one','account','{}',0)")
        now = [100]
        queue = QueueRepository(self.url, QueueSpec('social_events', completed='processed_at'), clock=lambda: now[0])
        with ThreadPoolExecutor(max_workers=4) as executor:
            claims = list(executor.map(lambda owner: queue.claim(owner, lease_seconds=3), ['a', 'b', 'c', 'd']))
        winners = [claim for claim in claims if claim is not None]
        self.assertEqual(len(winners), 1)
        stale = winners[0]
        now[0] = 104
        current = queue.claim('replacement', lease_seconds=3)
        self.assertEqual(current.id, stale.id)
        self.assertFalse(queue.finish(stale, Outcome()))
        self.assertTrue(queue.finish(current, Outcome(error='temporary', retry=True)))
        self.assertIsNone(queue.claim('early'))
        now[0] = 1000
        final = queue.claim('final')
        self.assertTrue(queue.finish(final, Outcome()))
        self.assertIsNone(queue.claim('done'))

    def test_resource_lease_expiry_and_stale_guard(self):
        from jobs.repository import ResourceLeaseRepository
        from jobs.models import LostLease
        apply(self.url)
        now = [100]
        first = ResourceLeaseRepository(self.url, 'test', 'one', seconds=3, clock=lambda: now[0])
        second = ResourceLeaseRepository(self.url, 'test', 'one', seconds=3, clock=lambda: now[0])
        first.acquire()
        with self.assertRaises(LostLease):
            second.acquire()
        now[0] = 104
        second.acquire()
        with self.assertRaises(LostLease):
            first.check()
        first.release()
        second.renew()
        second.check()
        second.release()

    def test_social_subscription_claim_event_and_oauth(self):
        from social.repository import SocialRepository
        apply(self.url)
        social = SocialRepository(self.url)
        sub = social.save_social_subscription_v2(1, 'x', 'account', 2, ['post'], {}, {})
        self.assertGreater(sub['id'], 0)
        with ThreadPoolExecutor(max_workers=3) as executor:
            claims = list(executor.map(lambda owner: social.claim_social_targets(owner), ['a', 'b', 'c']))
        targets = [target for group in claims for target in group]
        self.assertEqual(len(targets), 1)
        target = targets[0]
        self.assertTrue(social.complete_social_target(target['id'], target['lease_owner'], status='active', cursor={}, next_check_at=9999999999))
        self.assertTrue(social.enqueue_social_event_v2('x', 'event', 'account', 'post', {}))
        self.assertFalse(social.enqueue_social_event_v2('x', 'event', 'account', 'post', {}))
        self.assertTrue(social.record_social_delivery(sub['id'], 'x:post:event', 2, 3))
        self.assertFalse(social.record_social_delivery(sub['id'], 'x:post:event', 2, 3))
        social.create_social_oauth_state('state', 1, 'tiktok')
        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(lambda _: social.consume_social_oauth_state('state', 'tiktok'), range(3)))
        self.assertEqual(results.count(1), 1)
        self.assertEqual(results.count(None), 2)

    def test_moderation_points_receipt_and_upserts(self):
        from moderation.repository import ModerationRepository
        apply(self.url)
        moderation = ModerationRepository(self.url)
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: moderation.add_points(1, 2, 5, 'reason'), range(4)))
        self.assertEqual(sorted(before for _, before, _ in results), [0, 5, 10, 15])
        self.assertEqual(moderation.active_points(1, 2), 20)
        event = moderation.create_moderation_event(1, family='manual', event_type='ban', source='case_execution', reason='reason', dedupe_key='one')
        self.assertIsNotNone(event)
        self.assertIsNone(moderation.create_moderation_event(1, family='manual', event_type='ban', source='case_execution', reason='reason', dedupe_key='one'))
        with ThreadPoolExecutor(max_workers=3) as executor:
            cases = list(executor.map(lambda _: moderation.add_case(1, 2, 'tempban', 'reason', expires_at=1000, execution_event_id=event), range(3)))
        self.assertEqual(len(set(cases)), 1)
        with transaction(self.url) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) AS count FROM scheduled_moderation_actions').fetchone()['count'], 1)
        moderation.finish_moderation_event(event, [{'type': 'ban', 'status': 'sent', 'case_id': cases[0]}])
        moderation.finish_moderation_event(event, [{'type': 'ban', 'status': 'completed', 'case_id': cases[0]}])
        moderation.cache_url_result('hash', True)
        moderation.cache_url_result('hash', False)
        self.assertFalse(moderation.cached_url_result('hash'))
        with ThreadPoolExecutor(max_workers=3) as executor:
            lockdowns = list(executor.map(lambda _: moderation.start_lockdown(1, reason='reason', started_by=2, unlock_at=None), range(3)))
        self.assertEqual(len(set(lockdowns)), 1)
        moderation.save_lockdown_snapshot(lockdowns[0], 3, 4, {}, {})
        moderation.save_lockdown_snapshot(lockdowns[0], 3, 4, {}, {})
        self.assertEqual(len(moderation.lockdown_snapshots(lockdowns[0])), 1)

    def test_suggestion_votes_review_and_outbox(self):
        from suggestions.repository import SuggestionRepository
        apply(self.url)
        suggestions = SuggestionRepository(self.url)
        item = suggestions.create(1, 2, 3, {'title': 'Idea'})
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda user: suggestions.vote(1, item['id'], user, 1), range(10, 14)))
        self.assertEqual(suggestions.get(1, item['id'])['upvotes'], 4)
        self.assertEqual(suggestions.list(1)[0]['upvotes'], 4)
        suggestions.vote(1, item['id'], 10, 1)
        self.assertEqual(suggestions.get(1, item['id'])['upvotes'], 3)
        suggestions.review(1, item['id'], 20, 'approved', 'Accepted')
        with self.assertRaisesRegex(RuntimeError, 'suggestion_closed'):
            suggestions.vote(1, item['id'], 11, -1)
        claim = suggestions.outbox_jobs.claim('publisher')
        suggestions.publication_delivered(claim.payload, 100)
        self.assertEqual(suggestions.get(1, item['id'])['message_id'], 100)

    def test_reaction_role_message_revision_and_recovery(self):
        from reaction_roles.repository import ReactionRoleRepository
        apply(self.url)
        roles = ReactionRoleRepository(self.url)
        value = dict(channel_id=2, message_id=100, name='Roles', source='bot', behavior_type='normal',
            locked=False, access_policy='blacklist', selection_limit=None, temp_duration_seconds=None,
            self_destruct_at=None, embed={}, link_group_id=None, enabled=True, mappings=[],
            whitelist_role_ids=[200], blacklist_role_ids=[])
        first = roles.create_message(1, value)
        second = roles.create_message(1, {**value, 'message_id': 101})
        self.assertEqual(first['whitelist_role_ids'], [200])
        group = roles.create_link_group(1, 'Group', [first['id'], second['id']])
        self.assertEqual(len(group['message_ids']), 2)
        roles.dissolve_link_group(1, group['id'])
        current = roles.message(1, first['id'])
        updated = roles.update_message(1, first['id'], value, current['revision'])
        self.assertGreater(updated['revision'], current['revision'])
        with self.assertRaisesRegex(RuntimeError, 'revision_conflict'):
            roles.update_message(1, first['id'], value, current['revision'])
        roles.delete_message(1, first['id'], recoverable=True)
        self.assertIsNotNone(roles.recovery(1, 100))

    def test_ticket_reservation_receipts_and_transcript_versions(self):
        from ticketing.repository import TicketRepository
        apply(self.url)
        tickets = TicketRepository(self.url)
        tickets.save_settings(1, {'enabled': True, 'open_limit': 10})
        team = tickets.save_team(1, {'name': 'Staff', 'role_ids': [500]})
        panel = tickets.save_panel(1, {'name': 'Support', 'mode': 'channel', 'category_id': 100, 'team_id': team['id']})
        with ThreadPoolExecutor(max_workers=3) as executor:
            reservations = list(executor.map(lambda _: tickets.reserve_ticket(1, panel['id'], 10, 'one', {}), range(3)))
        self.assertEqual(len({item['id'] for item in reservations}), 1)
        ticket = tickets.activate_ticket(reservations[0]['id'], 700, 100)
        self.assertFalse(tickets.begin_delivery(ticket, 'welcome', 'container'))
        self.assertTrue(tickets.begin_delivery(ticket, 'welcome', 'container'))
        message = tickets.record_message(ticket['id'], 800, 10, 'User', 'encrypted', {'delivery_key': 'welcome'})
        self.assertEqual(tickets.record_message(ticket['id'], 800, 10, 'User', 'encrypted', {'delivery_key': 'welcome'}), message)
        self.assertTrue(tickets.delivery_recorded(ticket['id'], 'welcome'))
        with ThreadPoolExecutor(max_workers=3) as executor:
            transcripts = list(executor.map(lambda n: tickets.save_transcript(ticket['id'], 'local', str(n), 'hash', 10, 9999999999), range(3)))
        self.assertEqual(sorted(item['version'] for item in transcripts), [1, 2, 3])
        tickets.add_participant(ticket['id'], 'user', 20, 10)
        tickets.add_participant(ticket['id'], 'user', 20, 10, 'staff')
        tickets.record_orphan(1, ticket['id'], 900, 'channel', 'one')
        tickets.record_orphan(1, ticket['id'], 900, 'channel', 'two')
        self.assertEqual(len(tickets.pending_orphans(1)), 1)
        tickets.finish_notice(ticket, 'close-dm', {'id': 1234567890123456799})
        self.assertTrue(tickets.notice_message_recorded(ticket['id'], 1234567890123456799))
        self.assertFalse(tickets.notice_message_recorded(ticket['id'], 1234567890123456800))
        tickets.summary(1)
        tickets.statistics(1)

    def test_ticket_panel_origin_is_bound_to_saved_discord_message(self):
        from ticketing.repository import TicketRepository
        apply(self.url)
        tickets = TicketRepository(self.url)
        team = tickets.save_team(1, {'name': 'Staff', 'role_ids': [500]})
        panel = tickets.save_panel(1, {'name': 'Support', 'mode': 'channel', 'category_id': 100, 'team_id': team['id']})
        config = tickets.save_panel_message(1, {'name': 'Entry', 'channel_id': 10, 'panel_ids': [panel['id']], 'title': 'Support'})
        claim = tickets.claim_panel_messages('publisher')[0]
        self.assertTrue(tickets.mark_panel_published(claim, 900))
        self.assertTrue(tickets.panel_message_contains(1, 10, 900, panel['id']))
        for guild, channel, message in [(2, 10, 900), (1, 11, 900), (1, 10, 901)]:
            self.assertFalse(tickets.panel_message_contains(guild, channel, message, panel['id']))

    def test_social_concurrent_alias_resolution_keeps_one_canonical_target(self):
        from social.repository import SocialRepository
        apply(self.url)
        social = SocialRepository(self.url)
        first = social.save_social_subscription_v2(1, 'x', 'alias-one', 10, ['post'], {}, {})
        second = social.save_social_subscription_v2(2, 'x', 'alias-two', 20, ['post'], {}, {})
        targets = social.claim_social_targets('worker')
        self.assertEqual(len(targets), 2)
        def complete(target):
            return social.complete_social_target(target['id'], target['lease_owner'], status='active', cursor={}, next_check_at=9999999999, external_id='canonical')
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(list(executor.map(complete, targets)), [True, True])
        self.assertEqual(len(social.social_targets('x')), 1)
        self.assertEqual(social.social_subscription(first['id'])['target_id'], social.social_subscription(second['id'])['target_id'])
