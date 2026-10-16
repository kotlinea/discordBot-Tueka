"""Bounded Discord reads, live authorization, and safe public failure responses."""
import asyncio
import unittest
from unittest.mock import AsyncMock

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.api.route import ApiRoute
from dashboard.discord_api import DiscordAPI


class DiscordResilienceTests(unittest.IsolatedAsyncioTestCase):
    def api(self, replies):
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: replies.pop(0)))
        api = DiscordAPI('private-bot-token', '2', 'private-client-secret', 'https://example.test/callback')
        api._client = client
        self.addAsyncCleanup(api.close)
        return api

    async def test_rate_limited_read_retries_once_but_mutations_never_retry(self):
        replies = [httpx.Response(429, json={'retry_after': 0}), httpx.Response(200, json={'ok': True})]
        api = self.api(replies)
        self.assertEqual((await api._request('GET', '/test')).status_code, 200)
        self.assertEqual(replies, [])
        replies = [httpx.Response(429, json={'retry_after': 0}), httpx.Response(200)]
        api = self.api(replies)
        with self.assertRaises(httpx.HTTPStatusError):
            await api._request('POST', '/test', json={'content': 'never repeat'})
        self.assertEqual(len(replies), 1)

    async def test_long_malformed_and_repeated_limits_fail_without_unbounded_wait(self):
        for delay in (3, -1, 'nan', 'inf', None, 'not-a-number'):
            with self.subTest(delay=delay):
                replies = [httpx.Response(429, json={'retry_after': delay}), httpx.Response(200)]
                api = self.api(replies)
                with self.assertRaises(httpx.HTTPStatusError):
                    await asyncio.wait_for(api._request('GET', '/test'), 1)
                self.assertEqual(len(replies), 1)
        replies = [httpx.Response(429, json={'retry_after': 0}) for _ in range(3)]
        api = self.api(replies)
        with self.assertRaises(httpx.HTTPStatusError):
            await api._request('GET', '/test')
        self.assertEqual(len(replies), 1)

    async def test_retry_after_header_is_respected_without_parsing_html_body(self):
        replies = [httpx.Response(429, text='not JSON', headers={'Retry-After': '0'}),
                   httpx.Response(200)]
        self.assertEqual((await self.api(replies)._request('GET', '/test')).status_code, 200)
        self.assertEqual(replies, [])

    async def test_concurrent_read_checks_share_request_but_live_write_is_fresh(self):
        api = self.api([])
        gate = asyncio.Event()

        async def guilds(_token):
            await gate.wait()
            return [{'id': '10', 'permissions': '8'}]

        api.user_guilds = AsyncMock(side_effect=guilds)
        api.bot_guild_ids = AsyncMock(return_value={10})
        reads = [asyncio.create_task(api.can_manage('user-token', 10)) for _ in range(8)]
        for _ in range(5):
            await asyncio.sleep(0)
        live = asyncio.create_task(api.can_manage('user-token', 10, use_cache=False))
        for _ in range(5):
            await asyncio.sleep(0)
        self.assertEqual(api.user_guilds.await_count, 2)
        gate.set()
        self.assertEqual(await asyncio.gather(*reads, live), [True] * 9)
        self.assertFalse(api._manageable_inflight)
        api.bot_guild_ids.assert_any_await(use_cache=False)

    async def test_failed_authorization_is_not_cached_and_tokens_are_isolated(self):
        api = self.api([])
        api.user_guilds = AsyncMock(side_effect=httpx.ReadTimeout('private upstream message'))
        api.bot_guild_ids = AsyncMock(return_value={10})
        with self.assertRaises(httpx.ReadTimeout):
            await api.can_manage('first-token', 10)
        self.assertFalse(api._manageable_inflight)
        api.user_guilds = AsyncMock(return_value=[])
        self.assertFalse(await api.can_manage('first-token', 10))
        self.assertFalse(await api.can_manage('second-token', 10))
        self.assertEqual(api.user_guilds.await_count, 2)

    async def test_one_cancelled_reader_does_not_cancel_other_authorization(self):
        api = self.api([])
        gate = asyncio.Event()

        async def guilds(_token):
            await gate.wait()
            return [{'id': '10', 'permissions': '8'}]

        api.user_guilds = AsyncMock(side_effect=guilds)
        api.bot_guild_ids = AsyncMock(return_value={10})
        first = asyncio.create_task(api.can_manage('user-token', 10))
        second = asyncio.create_task(api.can_manage('user-token', 10))
        for _ in range(5):
            await asyncio.sleep(0)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        gate.set()
        self.assertTrue(await second)
        self.assertEqual(api.user_guilds.await_count, 1)


class UpstreamEnvelopeTests(unittest.TestCase):
    def test_long_upstream_delay_is_forwarded_as_safe_retry_header(self):
        request = httpx.Request('GET', 'https://discord.com/api/v10/users/@me/guilds')
        error = httpx.HTTPStatusError('PRIVATE_DETAIL', request=request,
            response=httpx.Response(429, json={'retry_after': 64.57}, request=request))
        app = FastAPI()
        app.router.route_class = ApiRoute

        @app.get('/probe')
        async def probe():
            raise error

        with TestClient(app) as client:
            response = client.get('/probe')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers['Retry-After'], '65')

    def test_only_rejected_user_oauth_requires_login_not_rejected_bot_credentials(self):
        for authorization, expected in (('Bearer PRIVATE_TOKEN', 401), ('Bot PRIVATE_TOKEN', 503)):
            request = httpx.Request('GET', 'https://discord.com/api/v10/users/@me/guilds',
                                    headers={'Authorization': authorization})
            error = httpx.HTTPStatusError('PRIVATE_DETAIL', request=request,
                response=httpx.Response(401, request=request))
            app = FastAPI()
            app.router.route_class = ApiRoute

            @app.get('/probe')
            async def probe():
                raise error

            with TestClient(app) as client:
                response = client.get('/probe')
            self.assertEqual(response.status_code, expected)
            self.assertNotIn('PRIVATE', response.text)

    def test_upstream_failure_is_503_without_request_or_response_secrets(self):
        request = httpx.Request('GET', 'https://discord.com/api/v10/users/@me/guilds?token=PRIVATE_QUERY',
                                headers={'Authorization': 'Bearer PRIVATE_TOKEN'})
        for error in (httpx.ReadTimeout('PRIVATE_DETAIL', request=request),
                      httpx.HTTPStatusError('PRIVATE_DETAIL', request=request,
                          response=httpx.Response(429, text='PRIVATE_BODY', request=request))):
            with self.subTest(error=type(error).__name__):
                app = FastAPI()
                app.router.route_class = ApiRoute

                @app.get('/probe')
                async def probe():
                    raise error

                with TestClient(app) as client:
                    response = client.get('/probe')
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()['detail']['code'], 'upstream_unavailable')
                self.assertNotIn('PRIVATE', response.text)
                self.assertNotIn('discord.com', response.text)
