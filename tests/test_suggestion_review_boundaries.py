"""Suggestion intake, OFF and out-of-order delivery regression boundaries."""
import asyncio
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from db_support import prepare_database
from guild_settings import GuildSettingsRepository
from jobs import LostLease, Outcome
from suggestions import SuggestionRepository
from suggestions.delivery import SuggestionDeliveryService
import test_suggestions_api
import test_suggestions_cog


class SyncOrderingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        url = prepare_database(Path(temp.name) / 'isolated-sync', self.addCleanup)
        repo = SuggestionRepository(url)
        settings = GuildSettingsRepository(url)
        settings.set_module(1, 'suggestions', enabled=True, settings={'channel_id': 10})
        item = repo.create(1, 10, 20, {'idea': 'Generated proposal'})
        publish = repo.outbox_jobs.claim('setup')
        repo.publication_delivered(publish.payload, 900)
        repo.outbox_jobs.finish(publish, Outcome())
        old_claim = repo.outbox_jobs.claim('old')
        self.assertEqual(old_claim.payload['action'], 'sync')
        self.repo, self.settings, self.item, self.claim = repo, settings, item, old_claim

    async def test_older_sync_cannot_leave_newer_review_stale(self):
        repo, settings, item, old_claim = self.repo, self.settings, self.item, self.claim
        entered, release = asyncio.Event(), asyncio.Event()

        class Port:
            rendered = None
            async def sync(self, snapshot, _settings):
                if snapshot['status'] == 'pending':
                    entered.set()
                    await release.wait()
                self.rendered = copy.deepcopy(snapshot)

        port = Port()
        delivery = SuggestionDeliveryService(repo, settings, port)
        stale = asyncio.create_task(delivery.deliver(old_claim.payload))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            current = repo.get(1, item['id'])
            repo.review(1, item['id'], 30, 'approved', 'Generated approval', expected_revision=current['revision'])
            newer = repo.outbox_jobs.claim('new')
            self.assertEqual(newer.payload['action'], 'sync')
            self.assertIsNone((await delivery.deliver(newer.payload)).error)
            self.assertTrue(repo.outbox_jobs.finish(newer, Outcome()))
            self.assertEqual(port.rendered['status'], 'approved')
            release.set()
            self.assertIsNone((await stale).error)
            self.assertTrue(repo.outbox_jobs.finish(old_claim, Outcome()))
            stored = repo.get(1, item['id'])
            # A stale external edit may need a repair job. Drain reservations
            # before checking convergence, including the review notification.
            for _ in range(20):
                repair = repo.outbox_jobs.claim('repair')
                if repair is None:
                    break
                result = await delivery.deliver(repair.payload)
                self.assertIsNone(result.error)
                self.assertTrue(repo.outbox_jobs.finish(repair, result))
            self.assertEqual(stored['status'], 'approved')
            self.assertEqual(port.rendered['status'], 'approved')
            with repo._connection() as c:
                self.assertEqual(c.execute("SELECT count(*) AS n FROM suggestion_outbox WHERE action='sync' AND status IN ('pending','retry','processing')").fetchone()['n'], 0)
        finally:
            release.set()
            if not stale.done():
                await stale

    async def test_vote_and_setting_changes_repair_even_without_item_revision_change(self):
        repo, settings, item = self.repo, self.settings, self.item
        initial_revision = repo.get(1, item['id'])['revision']

        class Port:
            rendered = None
            changed = False
            async def sync(self, snapshot, config):
                if not self.changed:
                    self.changed = True
                    repo.vote(1, item['id'], 40, 1)
                    settings.set_module(1, 'suggestions', enabled=True, settings={'channel_id': 10, 'show_author': False})
                self.rendered = (copy.deepcopy(snapshot), copy.deepcopy(config))

        port = Port()
        delivery = SuggestionDeliveryService(repo, settings, port)
        self.assertIsNone((await delivery.deliver(self.claim.payload)).error)
        self.assertTrue(repo.outbox_jobs.finish(self.claim, Outcome()))
        self.assertEqual(repo.get(1, item['id'])['revision'], initial_revision)
        for _ in range(20):
            claim = repo.outbox_jobs.claim('repair')
            if claim is None:
                break
            result = await delivery.deliver(claim.payload)
            self.assertIsNone(result.error)
            self.assertTrue(repo.outbox_jobs.finish(claim, result))
        self.assertEqual(port.rendered[0]['upvotes'], 1)
        self.assertFalse(port.rendered[1]['show_author'])

    async def test_repair_reservation_failure_does_not_report_delivery_success(self):
        repo, item = self.repo, self.item

        class Port:
            async def sync(self, _snapshot, _settings):
                repo.vote(1, item['id'], 40, 1)

        delivery = SuggestionDeliveryService(repo, self.settings, Port())
        with patch.object(repo, 'queue_sync', side_effect=RuntimeError('Generated enqueue failure')):
            with self.assertRaisesRegex(RuntimeError, 'Generated enqueue failure'):
                await delivery.deliver(self.claim.payload)
        self.assertTrue(repo.outbox_jobs.finish(self.claim, Outcome('Generated enqueue failure', retry=True)))
        with repo._connection() as c:
            state = c.execute('SELECT status FROM suggestion_outbox WHERE id=%s', (self.claim.id,)).fetchone()
        self.assertEqual(state['status'], 'retry')

    async def test_old_lease_cannot_reserve_a_presentation_repair(self):
        with self.repo._connection() as c:
            c.execute('UPDATE suggestion_outbox SET lease_until=0 WHERE id=%s', (self.claim.id,))
        newer = self.repo.outbox_jobs.claim('new')
        self.assertEqual(newer.id, self.claim.id)
        with self.assertRaises(LostLease):
            self.repo.queue_sync(1, self.item['id'], job=self.claim.payload)


class ReviewOffTests(unittest.TestCase):
    setUp = test_suggestions_api.SuggestionsApiTests.setUp

    def test_off_during_current_user_lookup_prevents_review(self):
        repo = SuggestionRepository(self.storage.database_url)
        self.storage.set_module(1, 'suggestions', enabled=True)
        item = repo.create(1, 10, 20, {'idea': 'Generated proposal'})
        # The awaited fake API is the synchronization point: OFF commits after
        # the route's enabled check and before Repository.review is entered.
        async def disable_before_returning_actor(_token):
            self.storage.set_module(1, 'suggestions', enabled=False)
            return {'id': '30'}
        self.discord.current_user.side_effect = disable_before_returning_actor
        response = self.client.post(
            f"/api/v1/guilds/1/suggestions/items/{item['id']}/review",
            json={'status': 'approved', 'reason': 'Generated approval', 'revision': item['revision']},
            headers={'x-csrf-token': 'test-csrf'},
        )
        self.assertFalse(self.storage.get_module(1, 'suggestions')['enabled'])
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(repo.get(1, item['id'])['status'], 'pending')
        self.assertEqual(len(repo.events(1, item['id'])), 1)


class IntakeRevisionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_suggestions_cog.SuggestionsCogTests.asyncSetUp
    interaction = test_suggestions_cog.SuggestionsCogTests.interaction

    async def test_open_form_field_replacement_requires_resubmission(self):
        old_settings = self.cog._settings(1)
        self.cog.guild_settings.set_module(1, 'suggestions', enabled=True, settings={
            'channel_id': 10,
            'form_fields': [{'key': 'new_optional', 'label': 'Generated replacement',
                             'style': 'paragraph', 'required': False, 'min_length': 0,
                             'max_length': 1000}],
        })
        interaction = self.interaction()
        await self.cog.submit_modal(interaction, old_settings, {'idea': 'User typed this answer into the open form'})
        saved = self.cog.repository.list(1)
        self.assertEqual(saved, [])
        self.channel.send.assert_not_awaited()
        interaction.response.send_message.assert_awaited_once()
        self.assertTrue(interaction.response.send_message.call_args.kwargs['ephemeral'])

    async def test_form_change_while_deferring_cannot_save_old_answers(self):
        old_settings = self.cog._settings(1)
        interaction = self.interaction()
        async def change_form(**_kwargs):
            self.cog.guild_settings.set_module(1, 'suggestions', enabled=True, settings={
                'channel_id': 10,
                'form_fields': [{'key': 'new_optional', 'label': 'Generated replacement',
                                 'style': 'paragraph', 'required': False, 'min_length': 0, 'max_length': 1000}],
            })
        interaction.response.defer.side_effect = change_form
        await self.cog.submit_modal(interaction, old_settings, {'idea': 'Generated answer'})
        self.assertEqual(self.cog.repository.list(1), [])
        self.channel.send.assert_not_awaited()
        interaction.followup.send.assert_awaited_once()

    async def test_off_while_deferring_cannot_save_a_submission(self):
        interaction = self.interaction()
        async def turn_off(**_kwargs):
            self.cog.guild_settings.set_module(1, 'suggestions', enabled=False)
        interaction.response.defer.side_effect = turn_off
        await self.cog.submit_modal(interaction, self.cog._settings(1), {'idea': 'Generated answer'})
        self.assertEqual(self.cog.repository.list(1), [])
        self.channel.send.assert_not_awaited()
        interaction.followup.send.assert_awaited_once()

    async def test_unchanged_form_keeps_the_submitted_answer(self):
        await self.cog.submit_modal(self.interaction(), self.cog._settings(1), {'idea': 'Generated answer'})
        saved = self.cog.repository.list(1)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]['answers'], {'idea': 'Generated answer'})
        self.assertIsNotNone(saved[0]['message_id'])

    async def test_delayed_vote_response_cannot_leave_approved_card_stale(self):
        repo = self.cog.repository
        item = repo.create(1, 10, 20, {'idea': 'Generated proposal'})
        item = repo.attach_message(1, item['id'], 100)
        interaction = self.interaction(f"tueka-suggestion:vote:{item['id']}:up")
        entered, release = asyncio.Event(), asyncio.Event()
        rendered = {'status': None}

        async def delayed_edit(**_payload):
            entered.set()
            await release.wait()
            rendered['status'] = 'pending'

        class Port:
            async def sync(self, snapshot, _settings):
                rendered['status'] = snapshot['status']

        async def drain():
            for _ in range(20):
                claim = repo.outbox_jobs.claim('worker')
                if claim is None:
                    break
                result = await self.cog.delivery.deliver(claim.payload)
                self.assertIsNone(result.error)
                self.assertTrue(repo.outbox_jobs.finish(claim, result))

        interaction.response.edit_message.side_effect = delayed_edit
        self.cog.delivery.port = Port()
        vote = asyncio.create_task(self.cog.on_interaction(interaction))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            current = repo.get(1, item['id'])
            repo.review(1, item['id'], 30, 'approved', 'Generated approval', expected_revision=current['revision'])
            await drain()
            self.assertEqual(rendered['status'], 'approved')
            release.set()
            await vote
            await drain()
            self.assertEqual(rendered['status'], 'approved')
        finally:
            release.set()
            if not vote.done():
                await vote


if __name__ == '__main__':
    unittest.main()
