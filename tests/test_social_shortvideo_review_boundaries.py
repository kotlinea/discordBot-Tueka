"""Offline short-video polling and checkpoint boundaries."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx

from db_support import prepare_database
from social import SocialRepository
from social.providers.instagram import InstagramAdapter
from social.providers.tiktok import TikTokAdapter


def rss(ids):
    return '<rss><channel>' + ''.join(
        f'<item><guid>{identifier}</guid><title>日本語😀 é</title>'
        f'<link>https://instagram.com/p/{identifier}</link></item>'
        for identifier in ids) + '</channel></rss>'


class ShortVideoReviewBoundaries(unittest.IsolatedAsyncioTestCase):
    async def instagram(self, text, target, *, initialize=False, status=200):
        settings = SimpleNamespace(instagram_rss_url_template='https://feeds.example/{account}', instagram_rss_auth_token='')
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(status, text=text))) as client:
            return await InstagramAdapter(settings, client).poll(target, initialize=initialize)

    async def test_instagram_initial_snapshot_over_twenty_stays_suppressed(self):
        text = rss([f'p{i}' for i in range(25, 0, -1)])
        first = await self.instagram(text, {'account_key': 'creator'}, initialize=True)
        self.assertEqual(first.events, [])
        self.assertEqual(len(first.cursor['seen']), 25)
        second = await self.instagram(text, {'account_key': 'creator', 'cursor': first.cursor})
        self.assertEqual(second.events, [])

    async def test_instagram_empty_snapshot_preserves_initial_checkpoint(self):
        first = await self.instagram(rss(['p2', 'p1']), {'account_key': 'creator'}, initialize=True)
        empty = await self.instagram(rss([]), {'account_key': 'creator', 'cursor': first.cursor})
        self.assertEqual(empty.cursor, first.cursor)
        restored = await self.instagram(rss(['p2', 'p1']), {'account_key': 'creator', 'cursor': empty.cursor})
        self.assertEqual(restored.events, [])

    async def test_instagram_old_twenty_cursor_suppresses_tail_and_keeps_new_head(self):
        old = {'seen': [f'p{i}' for i in range(21, 1, -1)]}
        target = {'account_key': 'creator', 'cursor': old}
        original = copy.deepcopy(target)
        result = await self.instagram(rss([f'p{i}' for i in range(23, 0, -1)]), target)
        self.assertEqual([event.external_id for event in result.events], ['p22', 'p23'])
        self.assertEqual(len(result.cursor['seen']), 23)
        self.assertEqual(target, original)

    async def test_instagram_retention_does_not_recreate_old_tail(self):
        repo = SocialRepository(prepare_database(self.id(), self.addCleanup))
        initial = await self.instagram(rss([f'p{i}' for i in range(25, 0, -1)]), {'account_key': 'creator'}, initialize=True)
        text = rss([f'p{i}' for i in range(26, 0, -1)])
        new = await self.instagram(text, {'account_key': 'creator', 'cursor': initial.cursor})
        self.assertEqual([event.external_id for event in new.events], ['p26'])
        event = new.events[0]
        self.assertTrue(repo.enqueue_social_event_v2('instagram', event.external_id, 'creator', 'post', event.payload))
        self.assertEqual(repo.pending_social_events()[0]['payload']['title'], '日本語😀 é')
        with repo._connection() as connection:
            connection.execute("UPDATE social_events SET processed_at=1,status='done'")
        self.assertEqual(repo.purge_social_history(retention_days=30), 1)
        after = await self.instagram(text, {'account_key': 'creator', 'cursor': new.cursor})
        self.assertEqual(after.events, [])

    async def test_instagram_http_errors_keep_input_checkpoint(self):
        for status in (403, 429, 500, 503):
            with self.subTest(status=status):
                target = {'account_key': 'creator', 'cursor': {'seen': ['old']}}
                original = copy.deepcopy(target)
                with self.assertRaises(httpx.HTTPStatusError):
                    await self.instagram(rss([]), target, status=status)
                self.assertEqual(target, original)

    async def test_instagram_missing_fields_and_duplicate_ids(self):
        text = '<rss><channel><item/><item><guid>p1</guid></item><item><guid>p1</guid></item></channel></rss>'
        result = await self.instagram(text, {'account_key': 'creator', 'cursor': {'seen': ['old']}})
        self.assertEqual([event.external_id for event in result.events], ['p1'])
        self.assertEqual(result.cursor['seen'], ['p1'])

    async def test_tiktok_live_id_replacement_ends_old_and_starts_new(self):
        adapter = TikTokAdapter(SimpleNamespace(), None)
        adapter._extract = AsyncMock(side_effect=[{'entries': []}, {'id': 'live2', 'is_live': True}])
        result = await adapter.poll({'account_key': 'creator', 'cursor': {'seen': [], 'live': True, 'live_id': 'live1'}}, initialize=False)
        self.assertEqual([(event.external_id, event.event_type) for event in result.events], [('live1', 'live_end'), ('live2', 'live_start')])
        self.assertEqual(result.cursor['live_id'], 'live2')

    async def test_tiktok_live_transition_controls_and_missing_id(self):
        cases = [
            ({'live': True, 'live_id': 'live1'}, {'id': 'live1', 'is_live': True}, [('live1', 'live_end')], None),
            ({'live': True, 'live_id': 'live1'}, {'id': 'live1', 'is_live': True}, [], 'live1'),
            ({'live': True, 'live_id': 'live1'}, {'is_live': True}, [], 'live1'),
            ({'live': True}, {'id': 'live1', 'is_live': True}, [], 'live1'),
            ({'live': False, 'live_id': 'live0'}, {'id': 'live1', 'is_live': True}, [('live1', 'live_start')], 'live1'),
        ]
        for cursor, live, expected, end_identity in cases:
            with self.subTest(cursor=cursor, live=live):
                adapter = TikTokAdapter(SimpleNamespace(), None)
                # First case verifies a normal live -> offline transition.
                adapter._extract = AsyncMock(side_effect=[{'entries': []}, None if end_identity is None else live])
                result = await adapter.poll({'account_key': 'creator', 'cursor': cursor}, initialize=False)
                self.assertEqual([(event.external_id, event.event_type) for event in result.events], expected)
                if end_identity:
                    self.assertEqual(result.cursor['live_id'], end_identity)

    async def test_tiktok_initial_live_and_posts_are_suppressed(self):
        adapter = TikTokAdapter(SimpleNamespace(), None)
        adapter._extract = AsyncMock(side_effect=[{'entries': [{'id': 'p1'}]}, {'id': 'live1', 'is_live': True}])
        result = await adapter.poll({'account_key': 'creator'}, initialize=True)
        self.assertEqual(result.events, [])
        self.assertEqual(result.cursor, {'seen': ['p1'], 'live': True, 'live_id': 'live1'})

    async def test_tiktok_acquisition_failure_keeps_input_checkpoint(self):
        for responses in ([RuntimeError('profile unavailable')], [{'entries': [{'id': 'p2'}]}, RuntimeError('live unavailable')]):
            with self.subTest(responses=responses):
                target = {'account_key': 'creator', 'cursor': {'seen': ['p1'], 'live': True, 'live_id': 'live1'}}
                original = copy.deepcopy(target)
                adapter = TikTokAdapter(SimpleNamespace(), None)
                adapter._extract = AsyncMock(side_effect=responses)
                with self.assertRaises(RuntimeError):
                    await adapter.poll(target, initialize=False)
                self.assertEqual(target, original)
