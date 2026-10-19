"""Provider acquisition contracts without credentials or external requests."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx

from social.providers.instagram import InstagramAdapter
from social.providers.tiktok import TikTokAdapter
from social.providers.twitch import TwitchAdapter
from social.providers.x import XAdapter
from social.providers.contracts import PollResult, SocialEvent
from social.worker import SocialWorker


class ProviderContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_without_checkpoint_still_initializes_without_notifications(self):
        worker = object.__new__(SocialWorker)
        worker.settings = SimpleNamespace(social_poll_interval_seconds=120)
        worker.repository = SimpleNamespace(complete_social_target=Mock(return_value=True))
        worker.failures = {}
        adapter = SimpleNamespace(poll=AsyncMock(return_value=PollResult({'since_id': '20'}, external_id='42')))
        target = {'id': 1, 'provider': 'x', 'status': 'pending', 'cursor': {},
                  'account_key': 'creator', 'lease_owner': 'fixture'}
        await worker._process_target(target, {'x': adapter})
        adapter.poll.assert_awaited_once_with(target, initialize=True)
        self.assertEqual(worker.repository.complete_social_target.call_args.kwargs['events'], [])

    async def test_manual_retry_with_saved_cursor_does_not_suppress_new_posts(self):
        worker = object.__new__(SocialWorker)
        worker.settings = SimpleNamespace(social_poll_interval_seconds=120)
        worker.repository = SimpleNamespace(complete_social_target=Mock(return_value=True))
        worker.failures = {}
        adapter = SimpleNamespace(poll=AsyncMock(return_value=PollResult(
            {'since_id': '20'}, [SocialEvent('20', 'post', {'title': 'New'})], external_id='42')))
        target = {'id': 1, 'provider': 'x', 'status': 'pending', 'cursor': {'since_id': '10'},
                  'account_key': 'creator', 'lease_owner': 'fixture'}
        await worker._process_target(target, {'x': adapter})
        adapter.poll.assert_awaited_once_with(target, initialize=False)
        self.assertEqual(worker.repository.complete_social_target.call_args.kwargs['events'][0]['external_id'], '20')

    async def test_x_resolves_identity_suppresses_initial_posts_and_does_not_backfill_initial_pages(self):
        requests = []
        def respond(request):
            requests.append(request)
            if '/by/username/' in request.url.path:
                return httpx.Response(200, json={'data': {'id': '42', 'username': 'creator', 'name': 'Creator'}})
            return httpx.Response(200, json={'data': [{'id': '30', 'text': 'latest'}], 'meta': {'next_token': 'older'}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await XAdapter(SimpleNamespace(x_bearer_token='fixture'), client).poll({'account_key': 'creator'}, initialize=True)
        self.assertEqual((result.external_id, result.cursor, result.events), ('42', {'since_id': '30'}, []))
        self.assertEqual(len(requests), 2)

    async def test_x_backfills_all_pages_oldest_first_and_deduplicates_boundary(self):
        requests = []
        def respond(request):
            requests.append(request)
            self.assertEqual(request.url.params['since_id'], '10')
            self.assertEqual(request.url.params['max_results'], '100')
            if request.url.params.get('pagination_token') == 'page2':
                return httpx.Response(200, json={'data': [{'id': '29'}, {'id': '28'}]})
            return httpx.Response(200, json={'data': [{'id': '30'}, {'id': '29'}], 'meta': {'next_token': 'page2'}})
        target = {'account_key': 'creator', 'external_id': '42', 'cursor': {'since_id': '10'}}
        original = copy.deepcopy(target)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await XAdapter(SimpleNamespace(x_bearer_token='fixture'), client).poll(target, initialize=False)
        self.assertEqual([event.external_id for event in result.events], ['28', '29', '30'])
        self.assertEqual(result.cursor, {'since_id': '30'})
        self.assertEqual(target, original)
        self.assertEqual(len(requests), 2)

    async def test_x_later_page_failure_keeps_original_cursor_for_retry(self):
        for status in (429, 503):
            with self.subTest(status=status):
                def respond(request):
                    if request.url.params.get('pagination_token'):
                        return httpx.Response(status)
                    return httpx.Response(200, json={'data': [{'id': '30'}], 'meta': {'next_token': 'next'}})
                target = {'account_key': 'creator', 'external_id': '42', 'cursor': {'since_id': '10'}}
                original = copy.deepcopy(target)
                async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                    with self.assertRaises(httpx.HTTPStatusError):
                        await XAdapter(SimpleNamespace(x_bearer_token='fixture'), client).poll(target, initialize=False)
                self.assertEqual(target, original)

    async def test_x_repeated_page_token_fails_without_advancing_cursor(self):
        def respond(request):
            return httpx.Response(200, json={'data': [{'id': '30'}], 'meta': {'next_token': 'same'}})
        target = {'account_key': 'creator', 'external_id': '42', 'cursor': {'since_id': '10'}}
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaisesRegex(RuntimeError, 'pagination'):
                await XAdapter(SimpleNamespace(x_bearer_token='fixture'), client).poll(target, initialize=False)
        self.assertEqual(target['cursor'], {'since_id': '10'})

    async def test_x_incomplete_or_unidentified_page_cannot_skip_posts(self):
        for page in ({'data': [{'id': '30'}], 'errors': [{'detail': 'partial'}]}, {'data': [{}]}, {'data': 'invalid'}):
            with self.subTest(page=page):
                target = {'account_key': 'creator', 'external_id': '42', 'cursor': {'since_id': '10'}}
                async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=page))) as client:
                    with self.assertRaises(RuntimeError):
                        await XAdapter(SimpleNamespace(x_bearer_token='fixture'), client).poll(target, initialize=False)
                self.assertEqual(target['cursor'], {'since_id': '10'})

    async def test_missing_provider_configuration_makes_no_external_request(self):
        request = AsyncMock(side_effect=AssertionError('Must not request an unconfigured provider'))
        client = SimpleNamespace(get=request, post=request)
        for adapter in (XAdapter(SimpleNamespace(x_bearer_token=''), client),
                        InstagramAdapter(SimpleNamespace(instagram_rss_url_template='http://feeds.example/{account}'), client),
                        TwitchAdapter(SimpleNamespace(twitch_client_id='', twitch_client_secret=''), client)):
            with self.subTest(provider=adapter.provider), self.assertRaises(RuntimeError):
                await adapter.poll({'account_key': 'creator'}, initialize=False)
        request.assert_not_awaited()

    async def test_instagram_initial_suppression_then_post_and_reel_in_order(self):
        feed = '<rss><channel><item><guid>r2</guid><link>https://instagram.com/reel/2</link></item><item><guid>p1</guid><link>https://instagram.com/p/1</link></item><item><guid>old</guid><link>https://instagram.com/p/0</link></item></channel></rss>'
        def respond(request):
            self.assertEqual(str(request.url), 'https://feeds.example/creator')
            return httpx.Response(200, text=feed)
        settings = SimpleNamespace(instagram_rss_url_template='https://feeds.example/{account}', instagram_rss_auth_token='')
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            adapter = InstagramAdapter(settings, client)
            initial = await adapter.poll({'account_key': 'creator'}, initialize=True)
            result = await adapter.poll({'account_key': 'creator', 'cursor': {'seen': ['old']}}, initialize=False)
        self.assertEqual(initial.events, [])
        self.assertEqual([(e.external_id, e.event_type) for e in result.events], [('p1', 'post'), ('r2', 'reel')])
        self.assertEqual(result.cursor['seen'], ['r2', 'p1', 'old'])

    async def test_instagram_rate_limit_preserves_seen_cursor(self):
        target = {'account_key': 'creator', 'cursor': {'seen': ['old']}}
        settings = SimpleNamespace(instagram_rss_url_template='https://feeds.example/{account}', instagram_rss_auth_token='')
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(429))) as client:
            with self.assertRaises(httpx.HTTPStatusError):
                await InstagramAdapter(settings, client).poll(target, initialize=False)
        self.assertEqual(target['cursor'], {'seen': ['old']})

    async def test_tiktok_ignores_unavailable_entries_without_losing_valid_posts(self):
        adapter = TikTokAdapter(SimpleNamespace(), None)
        adapter._extract = AsyncMock(side_effect=[{'entries': [None, {}, {'id': None}, 'unavailable', {'id': 'new'}, {'id': 'old'}]}, None])
        target = {'account_key': 'creator', 'cursor': {'seen': ['old']}}
        result = await adapter.poll(target, initialize=False)
        self.assertEqual(result.cursor['seen'], ['new', 'old'])
        self.assertEqual([e.external_id for e in result.events], ['new'])
        self.assertEqual(target['cursor'], {'seen': ['old']})

    async def test_tiktok_malformed_entries_preserve_cursor_for_retry(self):
        adapter = TikTokAdapter(SimpleNamespace(), None)
        adapter._extract = AsyncMock(return_value={'entries': {'id': 'invalid'}})
        target = {'account_key': 'creator', 'cursor': {'seen': ['old']}}
        with self.assertRaises(RuntimeError):
            await adapter.poll(target, initialize=False)
        self.assertEqual(target['cursor'], {'seen': ['old']})

    async def test_tiktok_initial_live_suppression_and_live_end_identity(self):
        adapter = TikTokAdapter(SimpleNamespace(), None)
        adapter._extract = AsyncMock(side_effect=[{'entries': [{'id': 'post'}]}, {'id': 'live1', 'is_live': True}, {'entries': []}, None])
        initial = await adapter.poll({'account_key': 'creator'}, initialize=True)
        ended = await adapter.poll({'account_key': 'creator', 'cursor': initial.cursor}, initialize=False)
        self.assertEqual(initial.events, [])
        self.assertEqual([(e.external_id, e.event_type) for e in ended.events], [('live1', 'live_end')])

    async def test_twitch_suppresses_initial_live_and_emits_start_end(self):
        for previous, stream, initialize, expected in [(False, {'id': 'live1'}, True, []), (False, {'id': 'live1'}, False, [('live1', 'live_start')]), (True, None, False, [('live0', 'live_end')])]:
            with self.subTest(previous=previous, stream=stream, initialize=initialize):
                def respond(request):
                    if request.url.path.endswith('/token'):
                        return httpx.Response(200, json={'access_token': 'fixture'})
                    if request.url.path.endswith('/users'):
                        return httpx.Response(200, json={'data': [{'id': '42', 'display_name': 'Creator', 'login': 'creator'}]})
                    return httpx.Response(200, json={'data': [stream] if stream else []})
                settings = SimpleNamespace(twitch_client_id='fixture', twitch_client_secret='fixture', dashboard_base_url='', social_webhook_secret='')
                async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                    result = await TwitchAdapter(settings, client).poll({'account_key': 'creator', 'cursor': {'live': previous, 'stream_id': 'live0'}}, initialize=initialize)
                self.assertEqual([(e.external_id, e.event_type) for e in result.events], expected)
