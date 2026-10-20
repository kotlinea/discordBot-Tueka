"""Insights settings across the real Discord resource adapter and API boundary."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from db_support import prepare_database
from dashboard.api.community.insights import create_router
from dashboard.api.community.ticket_support.resources import TicketResources
from dashboard.api.context import create_context
from dashboard.discord_api import DiscordAPI
from dashboard.repository import DashboardRepository


class InsightsResourceReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.url = prepare_database(Path(self.tmp.name) / 'insights-resources', self.addCleanup)
        DashboardRepository(self.url).create_dashboard_session('session', 'token', 3600)
        self.channels = [
            {'id': str(20 + kind), 'type': kind, 'nsfw': False}
            for kind in (0, 2, 4, 5, 13, 15, 16)
        ] + [{'id': '90', 'type': 15, 'nsfw': True}]
        self.discord = DiscordAPI('test-bot', '99', 'test-secret', 'https://example.invalid/callback')
        self.discord._request = AsyncMock(side_effect=self.request)
        self.discord.can_manage = AsyncMock(return_value=True)
        self.context = create_context(self.url, self.discord)
        app = FastAPI()

        @app.middleware('http')
        async def session(request, call_next):
            request.scope['session'] = {'session_id': 'session', 'csrf_token': 'csrf'}
            return await call_next(request)

        app.include_router(create_router(self.context), prefix='/api/v1')
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    async def request(self, method, path, **kwargs):
        if method != 'GET':
            raise AssertionError(f'Unexpected request method: {method}')
        data = {
            '/guilds/1/channels': self.channels,
            '/guilds/1/roles': [{'id': '1', 'name': '@everyone', 'permissions': '8', 'position': 0}],
            '/guilds/1/members/99': {'id': '99', 'roles': []},
        }
        return httpx.Response(200, json=data[path])

    def save(self, channel_id):
        revision = self.context.guild_settings_repository.get_module(1, 'insights')['revision']
        return self.client.put('/api/v1/guilds/1/insights/settings', headers={'x-csrf-token': 'csrf'}, json={
            'enabled': True,
            'revision': revision,
            'settings': {'channel_ids': [str(channel_id)], 'retention_days': 30, 'track_members': True},
        })

    def test_supported_channels_survive_real_resource_lookup_and_save(self):
        for kind in (0, 2, 5, 13, 15, 16):
            with self.subTest(channel_type=kind):
                response = self.save(20 + kind)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['settings']['channel_ids'], [str(20 + kind)])
        self.discord.can_manage.assert_awaited_with('token', 1, use_cache=False)

    def test_category_nsfw_and_missing_channels_remain_rejected(self):
        for channel_id in (24, 90, 999):
            with self.subTest(channel_id=channel_id):
                response = self.save(channel_id)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertFalse(self.context.guild_settings_repository.get_module(1, 'insights')['enabled'])

    def test_ticket_domain_keeps_its_own_channel_type_restrictions(self):
        import asyncio

        async def check():
            tickets = TicketResources(self.discord)
            await tickets.validate_ticket_resources(1, {'channel_id': 20, 'category_id': 24})
            for kind in (2, 5, 13, 15, 16):
                with self.subTest(channel_type=kind), self.assertRaises(ValueError):
                    await tickets.validate_ticket_resources(1, {'channel_id': 20 + kind})
                    
        asyncio.run(check())
