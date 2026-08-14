import asyncio
import time
import unittest
from pathlib import Path

import httpx

from dashboard.discord_api import DiscordAPI


class FakeDiscordClient:
    def __init__(self, delay: float = 0) -> None:
        self.delay, self.calls = delay, []

    async def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.delay:
            await asyncio.sleep(self.delay)
        if url.endswith("/users/@me"):
            payload = {"id": "1", "username": "Tueka"}
        elif url.endswith("/users/@me/guilds"):
            payload = [{"id": "10", "permissions": "8"}]
        elif url.endswith("/channels"):
            payload = [{"id": "100", "type": 0, "name": "general"}]
        elif url.endswith("/roles"):
            payload = [{"id": "1", "name": "@everyone", "permissions": "0", "position": 0}, {"id": "2", "name": "Bot", "permissions": "0", "position": 1}]
        elif "/members/" in url:
            payload = {"roles": ["2"]}
        else:
            raise AssertionError(url)
        return httpx.Response(200, json=payload, request=httpx.Request(method, url))


class DashboardPerformanceTests(unittest.IsolatedAsyncioTestCase):
    def api_with(self, client):
        api = DiscordAPI("bot-token", "2", "secret", "http://localhost/callback")
        api._client = client
        return api

    async def test_get_side_caches_reuse_discord_results(self):
        client = FakeDiscordClient()
        api = self.api_with(client)
        await api.manageable_guilds("user-token")
        await api.manageable_guilds("user-token")
        await api.guild_resources(10)
        await api.guild_resources(10)
        self.assertEqual(len(client.calls), 5)

    async def test_live_authorization_bypasses_get_cache(self):
        client = FakeDiscordClient()
        api = self.api_with(client)
        self.assertTrue(await api.can_manage("user-token", 10))
        self.assertTrue(await api.can_manage("user-token", 10, use_cache=False))
        self.assertEqual(len(client.calls), 4)

    async def test_live_authorization_refreshes_follow_up_get_cache(self):
        client = FakeDiscordClient()
        api = self.api_with(client)
        self.assertTrue(await api.can_manage("user-token", 10, use_cache=False))
        self.assertTrue(await api.can_manage("user-token", 10))
        self.assertEqual(len(client.calls), 2)

    async def test_expired_or_invalidated_cache_is_refetched(self):
        client = FakeDiscordClient()
        api = self.api_with(client)
        await api.bot_user()
        api._cache[("bot_user", "self")] = (0, {"id": "stale"})
        await api.bot_user()
        await api.guild_resources(10)
        api.invalidate_guild_resources(10)
        await api.guild_resources(10)
        self.assertEqual(len(client.calls), 8)

    async def test_guild_resources_are_requested_in_parallel(self):
        client = FakeDiscordClient(delay=0.1)
        api = self.api_with(client)
        started = time.perf_counter()
        await api.guild_resources(10, use_cache=False)
        self.assertLess(time.perf_counter() - started, 0.24)
        self.assertEqual(len(client.calls), 3)

    async def test_manageable_guild_sources_are_requested_in_parallel(self):
        client = FakeDiscordClient(delay=0.1)
        api = self.api_with(client)
        started = time.perf_counter()
        await api.manageable_guilds("user-token", use_cache=False)
        self.assertLess(time.perf_counter() - started, 0.24)
        self.assertEqual(len(client.calls), 2)

    def test_dashboard_script_does_not_fetch_identity(self):
        script = Path("dashboard/static/dashboard.js").read_text(encoding="utf-8")
        self.assertNotIn("/api/identity", script)
