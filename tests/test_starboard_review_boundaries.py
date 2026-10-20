"""Starboard regression boundaries with isolated PostgreSQL and fake Discord I/O."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from db_support import prepare_database
from database import transaction
from discord_io import DiscordFailure
from starboard.repository import StarboardRepository
from starboard.delivery import HighlightDelivery
from starboard.discord_adapter import DiscordHighlightAdapter, embed
from test_starboard_delivery import Adapter


async def users(values):
    for value in values:
        yield value


class StarboardAdapterBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def thread_adapter(self, private):
        target = MagicMock(spec=discord.Thread)
        target.guild = NS(id=1)
        target.type = discord.ChannelType.private_thread if private else discord.ChannelType.public_thread
        target.parent = NS(id=10, is_nsfw=lambda: False)
        target.parent_id = 10
        target.fetch_message = AsyncMock(return_value=NS(author=NS(id=40, bot=False, display_name='Proof'), content='Thread body', attachments=[], reactions=[]))
        adapter = DiscordHighlightAdapter(NS())
        adapter.channel = AsyncMock(return_value=target)
        return adapter, target

    async def test_private_thread_requires_explicit_id_before_reading_body(self):
        from starboard.models import eligible, normalize
        adapter, target = self.thread_adapter(True)
        parent = normalize({'name':'Proof', 'source_channel_ids':[10], 'target_channel_id':20})
        direct = normalize({'name':'Proof', 'source_channel_ids':[11], 'target_channel_id':20})
        snapshot, count = await adapter.source(1, 11, 100, '⭐')
        self.assertFalse(eligible(parent, snapshot))
        self.assertEqual((snapshot['content'], count), ('', 0))
        target.fetch_message.assert_not_awaited()
        snapshot, _ = await adapter.source(1, 11, 100, '⭐', True)
        self.assertTrue(eligible(direct, snapshot))
        self.assertFalse(eligible(parent, snapshot))
        self.assertEqual(snapshot['content'], 'Thread body')

    async def test_public_thread_still_inherits_parent_scope(self):
        from starboard.models import eligible, normalize
        adapter, target = self.thread_adapter(False)
        snapshot, _ = await adapter.source(1, 11, 100, '⭐')
        self.assertTrue(eligible(normalize({'name':'Proof', 'source_channel_ids':[10], 'target_channel_id':20}), snapshot))
        target.fetch_message.assert_awaited_once()

    async def test_channel_status_classification_preserves_nonmissing_failures(self):
        for status in (403, 404, 429, 500):
            with self.subTest(status=status):
                guild = NS(get_channel_or_thread=lambda _: None, fetch_channel=AsyncMock(side_effect=discord.HTTPException(NS(status=status, reason='Proof'), 'Proof')))
                adapter = DiscordHighlightAdapter(NS(get_guild=lambda _: guild))
                with self.assertRaises(DiscordFailure) as caught:
                    await adapter.channel(1, 10)
                self.assertEqual(caught.exception.missing, status == 404)
                self.assertEqual(caught.exception.retry, status in (429, 500))
                self.assertFalse(caught.exception.partial)

    async def test_custom_emoji_id_still_counts_with_unrelated_unicode(self):
        adapter, target = self.thread_adapter(False)
        target.fetch_message.return_value.reactions = [NS(emoji='↔️'), NS(emoji=discord.PartialEmoji(name='proof', id=123), users=lambda **_: users([NS(id=41, bot=False)]))]
        _, count = await adapter.source(1, 11, 100, 'custom:123')
        self.assertEqual(count, 1)

    async def test_unrelated_valid_discord_emoji_must_not_abort_star_count(self):
        target = MagicMock(spec=discord.TextChannel)
        target.guild = NS(id=1)
        target.is_nsfw.return_value = False
        other = NS(emoji='↔️', users=lambda **_: users([]))
        star = NS(emoji='⭐', users=lambda **_: users([NS(id=2, bot=False)]))
        source = NS(author=NS(id=1, bot=False, display_name='Proof'), content='Proof', attachments=[], reactions=[other, star])
        target.fetch_message = AsyncMock(return_value=source)
        adapter = DiscordHighlightAdapter(NS())
        adapter.channel = AsyncMock(return_value=target)
        _, count = await adapter.source(1, 10, 100, '⭐')
        self.assertEqual(count, 1)

    def test_embed_max_snapshot_stays_below_combined_budget(self):
        value = embed({'guild_id':1, 'channel_id':10, 'message_id':100, 'content':'x'*2000, 'author_name':'a'*80}, 5000, '⭐', 'Tueka highlight:999:999')
        self.assertLessEqual(len(value), 6000)
        self.assertLessEqual(len(value.description), 4096)


class StarboardReviewBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.url = prepare_database(Path(self.tmp.name) / 'starboard-independent', self.addCleanup)
        self.now = 1000
        self.repo = StarboardRepository(self.url, clock=lambda: self.now)
        self.repo.settings.set_module(1, 'starboard', enabled=True, settings={})
        self.config = {'name':'Proof', 'enabled':True, 'target_channel_id':20, 'source_channel_ids':[10], 'threshold':2, 'retention_days':1}
        self.board = self.repo.save_board(1, 30, self.config)
        self.source = {'guild_id':1, 'channel_id':10, 'message_id':100, 'author_id':40, 'author_bot':False, 'content':'Proof'}
        self.entry = self.repo.observe(1, self.board['id'], 1, self.source, 2)
        self.adapter = Adapter(self.source)
        self.delivery = HighlightDelivery(self.repo, self.adapter)

    async def process(self):
        claim = self.repo.jobs.claim('independent-review')
        self.assertIsNotNone(claim)
        outcome = await self.delivery.handle(claim.payload)
        self.assertTrue(self.repo.jobs.finish(claim, outcome))
        return outcome

    async def test_expiry_then_same_source_event_does_not_duplicate_retained_highlight(self):
        self.assertIsNone((await self.process()).error)
        self.now = self.entry['expires_at']
        self.assertIsNone(self.repo.observe(1, self.board['id'], 1, self.source, 2))
        self.assertEqual(self.repo.purge_expired(), 1)
        self.assertIsNone(self.repo.observe(1, self.board['id'], 1, self.source, 2))
        self.assertIsNone(self.repo.jobs.claim('expired-source'))
        self.assertEqual(len(self.adapter.sent), 1, 'Tracking ended at retention expiry; the retained highlight must not be duplicated')

    async def test_expired_marker_contains_only_ids_and_is_board_scoped(self):
        await self.process()
        self.now = self.entry['expires_at']
        self.assertEqual(self.repo.purge_expired(), 1)
        with transaction(self.url) as c:
            self.assertEqual(c.execute('SELECT * FROM starboard_expired_sources').fetchall(), [{'board_id':self.board['id'], 'source_message_id':100}])
            for table in ('starboard_entries', 'starboard_publications', 'starboard_events', 'starboard_outbox'):
                where = ' WHERE entry_id IS NOT NULL' if table == 'starboard_events' else ''
                self.assertEqual(c.execute('SELECT count(*) AS n FROM '+table+where).fetchone()['n'], 0)
        second = self.repo.save_board(1, 30, self.config)
        self.assertIsNotNone(self.repo.observe(1, second['id'], 1, self.source, 2))
        with transaction(self.url) as c:
            c.execute('DELETE FROM starboards WHERE id=%s', (self.board['id'],))
            self.assertEqual(c.execute('SELECT count(*) AS n FROM starboard_expired_sources').fetchone()['n'], 0)

    async def test_concurrent_purge_and_observation_do_not_resurrect_source(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        await self.process()
        self.now = self.entry['expires_at']
        barrier = Barrier(2)
        def purge():
            barrier.wait(timeout=10)
            return self.repo.purge_expired()
        def observe():
            barrier.wait(timeout=10)
            return self.repo.observe(1, self.board['id'], 1, self.source, 2)
        with ThreadPoolExecutor(2) as pool:
            purging, observing = pool.submit(purge), pool.submit(observe)
            purging.result(timeout=20)
            self.assertIsNone(observing.result(timeout=20))
        self.repo.purge_expired()
        self.assertIsNone(self.repo.observe(1, self.board['id'], 1, self.source, 2))
        self.assertIsNone(self.repo.jobs.claim('after-purge-race'))

    async def test_gateway_private_parent_is_skipped_but_explicit_thread_is_read(self):
        from cogs.engagement.starboard import StarboardCog
        target = MagicMock(spec=discord.Thread)
        target.guild = NS(id=1)
        target.type = discord.ChannelType.private_thread
        target.parent_id = 10
        target.parent = NS(id=10, is_nsfw=lambda: False)
        target.fetch_message = AsyncMock(return_value=NS(author=NS(id=40, bot=False, display_name='Private'), content='Private body', attachments=[], reactions=[NS(emoji='⭐', users=lambda **_: users([NS(id=41, bot=False), NS(id=42, bot=False)]))]))
        cog = StarboardCog(NS(settings=NS(database_url=self.url)))
        cog.repository, cog.delivery = self.repo, self.delivery
        cog.adapter.channel = AsyncMock(return_value=target)
        self.repo.enqueue_refresh(1, 11, 101, known_channel=True, parent=10)
        claim = self.repo.refresh_jobs.claim('private-parent')
        outcome = await cog.refresh_job(claim.payload)
        self.assertIsNone(outcome.error)
        self.assertTrue(self.repo.refresh_jobs.finish(claim, outcome))
        target.fetch_message.assert_not_awaited()
        self.assertEqual(len(self.repo.entries(1, self.board['id'])), 1)
        self.repo.save_board(1, 30, {**self.config, 'source_channel_ids':[11]}, board=self.board['id'], revision=1)
        self.repo.enqueue_refresh(1, 11, 101)
        claim = self.repo.refresh_jobs.claim('private-explicit')
        self.assertIsNone((await cog.refresh_job(claim.payload)).error)
        target.fetch_message.assert_awaited_once()
        private = next(row for row in self.repo.entries(1, self.board['id']) if row['source_message_id'] == 101)
        self.assertEqual(private['snapshot']['content'], 'Private body')

    async def test_external_success_receipt_db_failure_reconciles_without_second_send(self):
        original = self.repo.publication_receipt
        calls = 0
        def fail_once(*args):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError('Generated DB failure after send')
            return original(*args)
        with patch.object(self.repo, 'publication_receipt', side_effect=fail_once):
            self.assertTrue((await self.process()).retry)
        self.now += 100
        self.delivery = HighlightDelivery(self.repo, self.adapter)
        self.assertIsNone((await self.process()).error)
        self.assertEqual(len(self.adapter.sent), 1)

    async def test_missing_source_before_send_does_not_publish_stale_snapshot(self):
        async def missing(*_):
            raise DiscordFailure('Source missing', missing=True)
        self.adapter.source = missing
        self.assertIsNone((await self.process()).error)
        self.assertEqual(self.adapter.sent, [])
        self.assertTrue(self.repo.entries(1, self.board['id'])[0]['snapshot']['deleted'])

    async def test_source_delete_during_send_keeps_successor_and_withdraws(self):
        entered, release = asyncio.Event(), asyncio.Event()
        original = self.adapter.send
        async def gated(*args):
            entered.set()
            await release.wait()
            return await original(*args)
        self.adapter.send = gated
        task = asyncio.create_task(self.process())
        await entered.wait()
        self.repo.delete_source(1, 10, [100])
        release.set()
        await task
        await self.process()
        self.assertEqual(len(self.adapter.sent), 1)
        self.assertEqual(self.adapter.messages, {})

    async def test_real_channel_404_marks_known_source_deleted(self):
        await self.process()
        from cogs.engagement.starboard import StarboardCog
        guild = NS(get_channel_or_thread=lambda _: None,
                   fetch_channel=AsyncMock(side_effect=discord.NotFound(NS(status=404, reason='Gone'), 'Generated missing channel')))
        bot = NS(settings=NS(database_url=self.url), get_guild=lambda _: guild)
        cog = StarboardCog(bot)
        cog.repository = self.repo
        cog.delivery = self.delivery
        self.repo.enqueue_refresh(1, 10, 100)
        claim = self.repo.refresh_jobs.claim('source-review')
        self.assertIsNotNone(claim)
        outcome = await cog.refresh_job(claim.payload)
        self.assertIsNone(outcome.error)
        self.assertTrue(self.repo.entries(1, self.board['id'])[0]['snapshot']['deleted'])
        await self.process()
        self.assertEqual(self.adapter.messages, {})

    async def test_expired_lease_rejects_old_worker_receipt(self):
        claim = self.repo.jobs.claim('old-worker', lease_seconds=3)
        publication, _ = self.repo.publication_begin(claim.payload, 20)
        self.now += 3
        successor = self.repo.jobs.claim('new-worker', lease_seconds=60)
        self.assertIsNotNone(successor)
        from jobs import LostLease
        with self.assertRaises(LostLease):
            self.repo.publication_receipt(claim.payload, publication['id'], 999)


class StarboardExpiryMigrationTests(unittest.TestCase):
    def test_upgrade_from_four_migrations_preserves_records_and_reapplies(self):
        from database import connect
        from database.migrations import apply, load
        from database.testing import temporary_database
        with temporary_database(migrate=False) as url, tempfile.TemporaryDirectory() as old:
            directory = Path(old)
            for _, name, _, source in load()[:4]:
                (directory / name).write_text(source, encoding='utf-8')
            apply(url, directory)
            with connect(url) as c:
                board = c.execute("INSERT INTO starboards(guild_id,actor_id,request_key,config_json,created_at,updated_at) VALUES(1,30,'migration-proof','{}',1,1) RETURNING id").fetchone()['id']
                entry = c.execute("INSERT INTO starboard_entries(board_id,guild_id,source_channel_id,source_message_id,snapshot_json,score,desired,created_at,updated_at,expires_at) VALUES(%s,1,10,100,'{\"content\":\"Retained proof\",\"author_id\":40}',2,1,1,1,1000) RETURNING id", (board,)).fetchone()['id']
                c.execute("INSERT INTO app_metadata VALUES('starboard-upgrade','preserved')")
            self.assertIn('0005_starboard_expired_sources.sql', apply(url)['applied'])
            self.assertEqual(apply(url), {'applied':[]})
            with connect(url) as c:
                self.assertEqual(c.execute('SELECT snapshot_json FROM starboard_entries WHERE id=%s', (entry,)).fetchone()['snapshot_json'], '{"content":"Retained proof","author_id":40}')
                self.assertEqual(c.execute("SELECT value FROM app_metadata WHERE key='starboard-upgrade'").fetchone()['value'], 'preserved')
            self.assertEqual(StarboardRepository(url, clock=lambda:1000).purge_expired(), 1)
            with connect(url) as c:
                self.assertEqual(c.execute('SELECT * FROM starboard_expired_sources').fetchall(), [{'board_id':board, 'source_message_id':100}])


if __name__ == '__main__':
    unittest.main(verbosity=2)




