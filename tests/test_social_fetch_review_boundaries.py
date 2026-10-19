import asyncio
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
from social.providers.youtube import YouTubeAdapter
from social.providers.twitch import TwitchAdapter
from social.worker import SocialWorker
from social.repository import SocialRepository
from social.models import default_templates
from database.testing import temporary_database

CHANNEL = 'UC1234567890123456789012'
def yt_settings(api=None):
    return SimpleNamespace(youtube_api_key=api, dashboard_base_url='', social_webhook_secret='')
def feed(ids):
    entries = ''.join(f'<entry><yt:videoId>{i}</yt:videoId><yt:channelId>{CHANNEL}</yt:channelId><title>{i}</title><link href="https://youtu.be/{i}"/><author><name>Creator</name></author><published>2020-01-01T00:00:00Z</published></entry>' for i in ids)
    return f'<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015">{entries}</feed>'
def yt_target(cursor):
    return {'account_key': CHANNEL, 'external_id': CHANNEL, 'cursor': cursor}
def twitch_settings():
    return SimpleNamespace(twitch_client_id='offline-fixture', twitch_client_secret='offline-fixture', dashboard_base_url='', social_webhook_secret='')

class SocialFetchReviewBoundaries(unittest.IsolatedAsyncioTestCase):
    async def test_youtube_empty_then_recovered_baseline_video_stays_suppressed(self):
        pages = iter([feed(['old']), feed([]), feed(['old'])])
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=next(pages)))) as client:
            adapter = YouTubeAdapter(yt_settings(), client)
            initial = await adapter.poll(yt_target({}), initialize=True)
            empty = await adapter.poll(yt_target(initial.cursor), initialize=False)
            recovered = await adapter.poll(yt_target(empty.cursor), initialize=False)
        self.assertEqual(initial.events, [])
        self.assertIn('old', empty.cursor['seen'])
        self.assertEqual(recovered.events, [])

    async def test_youtube_previous_live_outside_feed_is_queried_and_retained_if_missing(self):
        queried = []
        ids = [f'new-{i}' for i in range(15)]
        def respond(req):
            if req.url.path.endswith('/videos'):
                queried.extend(req.url.params['id'].split(','))
                return httpx.Response(200, json={'items': []})
            return httpx.Response(200, text=feed(ids))
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await YouTubeAdapter(yt_settings('offline-fixture'), client).poll(yt_target({'seen': ids, 'live_ids': ['old-live'], 'feed_ready': True}), initialize=False)
        self.assertIn('old-live', queried)
        self.assertEqual(result.cursor['live_ids'], ['old-live'])
        self.assertFalse(any(e.event_type == 'live_end' for e in result.events))

    async def test_twitch_new_stream_between_polls_emits_end_then_start(self):
        def respond(req):
            if req.url.path.endswith('/token'): return httpx.Response(200, json={'access_token': 'offline'})
            if req.url.path.endswith('/users'): return httpx.Response(200, json={'data': [{'id': '42', 'login': 'creator', 'display_name': 'Creator'}]})
            return httpx.Response(200, json={'data': [{'id': 'new-stream', 'started_at': '2026-10-19T00:01:00Z'}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await TwitchAdapter(twitch_settings(), client).poll({'account_key': 'creator', 'external_id': '42', 'cursor': {'live': True, 'stream_id': 'old-stream'}}, initialize=False)
        self.assertEqual([(e.external_id, e.event_type) for e in result.events], [('old-stream', 'live_end'), ('new-stream', 'live_start')])
        self.assertEqual(result.cursor['stream_id'], 'new-stream')

    async def test_twitch_existing_external_identity_is_authoritative(self):
        queries = []
        def respond(req):
            if req.url.path.endswith('/token'): return httpx.Response(200, json={'access_token': 'offline'})
            if req.url.path.endswith('/users'):
                queries.append(dict(req.url.params))
                user = {'id': '42', 'login': 'renamed', 'display_name': 'Creator'} if req.url.params.get('id') == '42' else {'id': '99', 'login': 'creator', 'display_name': 'Different person'}
                return httpx.Response(200, json={'data': [user]})
            return httpx.Response(200, json={'data': [{'id': 'wrong-person-stream'}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await TwitchAdapter(twitch_settings(), client).poll({'account_key': 'creator', 'external_id': '42', 'cursor': {'live': False}}, initialize=False)
        self.assertEqual(queries, [{'id': '42'}])
        self.assertEqual(result.external_id, '42')
        self.assertEqual(result.handle, 'renamed')

class SocialTargetReviewBoundaries(unittest.IsolatedAsyncioTestCase):
    async def test_orphan_reregister_resumes_polling(self):
        with temporary_database() as url:
            repo = SocialRepository(url)
            sub = repo.save_social_subscription_v2(1, 'youtube', CHANNEL, 10, ['video'], {}, default_templates('youtube', ['video']))
            repo.delete_social_subscription(1, sub['id'])
            replacement = repo.save_social_subscription_v2(2, 'youtube', CHANNEL, 20, ['video'], {}, default_templates('youtube', ['video']))
            target = repo.claim_social_targets('offline-worker')[0]
            self.assertEqual(target['status'], 'pending')
            self.assertEqual(target['id'], replacement['target_id'])

class YouTubeLiveBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_initial_empty_feed_then_first_video_is_new(self):
        pages = iter([feed([]), feed(['first'])])
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=next(pages)))) as client:
            adapter = YouTubeAdapter(yt_settings(), client)
            initial = await adapter.poll(yt_target({}), initialize=True)
            result = await adapter.poll(yt_target(initial.cursor), initialize=False)
        self.assertEqual(initial.events, [])
        self.assertEqual([(e.external_id, e.event_type) for e in result.events], [('first', 'video')])

    async def test_live_outside_feed_ends_only_when_explicitly_ended(self):
        for details, expected_ids, expected_events in [
            ({'actualStartTime': '2026-10-19T00:00:00Z'}, ['old-live'], []),
            ({'actualStartTime': '2026-10-19T00:00:00Z', 'actualEndTime': '2026-10-19T01:00:00Z'}, [], [('old-live', 'live_end')]),
        ]:
            with self.subTest(details=details):
                queries = []
                def respond(req):
                    if req.url.path.endswith('/videos'):
                        queries.append(req.url.params['id'].split(','))
                        return httpx.Response(200, json={'items': [{'id': 'old-live', 'snippet': {'title': 'Stream', 'channelTitle': 'Creator'}, 'liveStreamingDetails': details}]})
                    return httpx.Response(200, text=feed([]))
                async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                    result = await YouTubeAdapter(yt_settings('offline-fixture'), client).poll(yt_target({'seen': ['old-live'], 'feed_ready': True, 'live_ids': ['old-live']}), initialize=False)
                self.assertEqual(queries, [['old-live']])
                self.assertEqual(result.cursor['live_ids'], expected_ids)
                self.assertEqual([(e.external_id, e.event_type) for e in result.events], expected_events)

    async def test_live_status_http_failure_keeps_original_cursor(self):
        for code in (403, 429, 503):
            with self.subTest(code=code):
                target = yt_target({'seen': ['old-live'], 'feed_ready': True, 'live_ids': ['old-live']})
                original = copy.deepcopy(target)
                def respond(req):
                    return httpx.Response(code) if req.url.path.endswith('/videos') else httpx.Response(200, text=feed([]))
                async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                    with self.assertRaises(httpx.HTTPStatusError):
                        await YouTubeAdapter(yt_settings('offline-fixture'), client).poll(target, initialize=False)
                self.assertEqual(target, original)

    async def test_live_queries_are_deduplicated_and_batched_and_later_failure_is_atomic(self):
        target = yt_target({'seen': ['old-0'], 'feed_ready': True, 'live_ids': [f'old-{i}' for i in range(55)]})
        original = copy.deepcopy(target)
        queries = []
        def respond(req):
            if req.url.path.endswith('/videos'):
                queries.append(req.url.params['id'].split(','))
                return httpx.Response(503) if len(queries) == 2 else httpx.Response(200, json={'items': []})
            return httpx.Response(200, text=feed(['old-0']))
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaises(httpx.HTTPStatusError):
                await YouTubeAdapter(yt_settings('offline-fixture'), client).poll(target, initialize=False)
        self.assertEqual([len(q) for q in queries], [50, 5])
        self.assertEqual(len(set(sum(queries, []))), 55)
        self.assertEqual(target, original)
class SocialCleanupRaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_old_cleanup_finishing_after_reregister_forces_resubscribe(self):
        with temporary_database() as url:
            repo = SocialRepository(url)
            sub = repo.save_social_subscription_v2(1, 'youtube', CHANNEL, 10, ['video'], {}, default_templates('youtube', ['video']))
            repo.delete_social_subscription(1, sub['id'])
            cleanup = repo.claim_social_targets('cleanup')[0]
            started, release = asyncio.Event(), asyncio.Event()
            async def unsubscribe(target):
                started.set()
                await release.wait()
            worker = object.__new__(SocialWorker)
            worker.repository = repo
            task = asyncio.create_task(worker._process_target(cleanup, {'youtube': SimpleNamespace(unsubscribe=unsubscribe)}))
            await started.wait()
            try:
                repo.save_social_subscription_v2(2, 'youtube', CHANNEL, 20, ['video'], {}, default_templates('youtube', ['video']))
                repo.request_social_target_retry(cleanup['id'])
                current = repo.claim_social_targets('new-monitor')[0]
                self.assertTrue(repo.complete_social_target(current['id'], current['lease_owner'], status='active', cursor={'seen': ['old'], 'feed_ready': True, 'websub_renew_at': 9999999999, 'eventsub_synced_at': 9999999999}, next_check_at=9999999999))
            finally:
                release.set()
                await task
            revived = repo.social_target(cleanup['id'])
            self.assertEqual(revived['status'], 'pending')
            self.assertEqual(revived['next_check_at'], 0)
            self.assertIsNone(revived['lease_owner'])
            self.assertEqual(revived['cursor']['seen'], ['old'])
            self.assertNotIn('websub_renew_at', revived['cursor'])
            self.assertNotIn('eventsub_synced_at', revived['cursor'])
class YouTubeBaselineCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_cursor_keeps_baseline_across_shrinking_feed(self):
        pages = iter([feed(['first']), feed(['second', 'first'])])
        target = yt_target({'seen': ['second', 'first'], 'live_ids': [], 'feed_ready': True})
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=next(pages)))) as client:
            adapter = YouTubeAdapter(yt_settings(), client)
            shrunk = await adapter.poll(target, initialize=False)
            recovered = await adapter.poll(yt_target(shrunk.cursor), initialize=False)
        self.assertEqual(shrunk.events, [])
        self.assertEqual(recovered.events, [])
        self.assertEqual(recovered.cursor['baseline_seen'], ['second', 'first'])

    async def test_unchanged_live_and_empty_details_do_not_repeat_start(self):
        def respond(req):
            if req.url.path.endswith('/videos'):
                self.assertEqual(req.url.params['id'], 'old-live')
                return httpx.Response(200, json={'items': []})
            return httpx.Response(200, text=feed(['old-live']))
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await YouTubeAdapter(yt_settings('offline-fixture'), client).poll(yt_target({'seen': ['old-live'], 'live_ids': ['old-live']}), initialize=False)
        self.assertEqual(result.events, [])
        self.assertEqual(result.cursor['live_ids'], ['old-live'])
class YouTubeInitializationRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_initialized_feed_keeps_baseline_through_source_outage(self):
        responses = iter([httpx.Response(200, text=feed([])), httpx.Response(404), httpx.Response(200, text=feed(['first']))])
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: next(responses))) as client:
            adapter = YouTubeAdapter(yt_settings(), client)
            adapter._yt_dlp_entries = AsyncMock(return_value=None)
            adapter._channel_exists_publicly = AsyncMock(return_value=True)
            with patch('social.providers.youtube.time.time', return_value=1000000):
                initial = await adapter.poll(yt_target({}), initialize=True)
                outage = await adapter.poll(yt_target(initial.cursor), initialize=False)
            self.assertTrue(outage.cursor['feed_ready'])
            with patch('social.providers.youtube.time.time', return_value=1021601):
                recovered = await adapter.poll(yt_target(outage.cursor), initialize=False)
        self.assertEqual([(e.external_id, e.event_type) for e in recovered.events], [('first', 'video')])
if __name__ == '__main__':
    unittest.main(verbosity=2)






