import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from db_support import prepare_database
from dashboard.api.context import create_context
from dashboard.api.community.insights import create_router
from dashboard.repository import DashboardRepository


class InsightsApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.url = prepare_database(Path(self.tmp.name) / 'insights-api', self.addCleanup)
        DashboardRepository(self.url).create_dashboard_session('session', 'token', 3600)
        self.session = {'session_id': 'session', 'csrf_token': 'csrf'}
        self.discord = SimpleNamespace(can_manage=AsyncMock(return_value=True), guild_resources=AsyncMock(return_value=(
            [{'id': '20', 'type': 0}, {'id': '21', 'type': 2}, {'id': '22', 'type': 4}, {'id': '23', 'type': 0, 'nsfw': True}], [], 8)))
        self.context = create_context(self.url, self.discord)
        app = FastAPI()
        @app.middleware('http')
        async def session(request, next):
            request.scope['session'] = self.session
            return await next(request)
        app.include_router(create_router(self.context), prefix='/api/v1')
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.base = '/api/v1/guilds/1/insights'
        self.body = {'enabled': True, 'settings': {'channel_ids': ['20', '21'], 'retention_days': 30, 'track_members': True}, 'revision': 0}
        self.headers = {'x-csrf-token': 'csrf'}

    def test_settings_csrf_revision_and_live_manager_access(self):
        self.assertEqual(self.client.put(self.base + '/settings', json=self.body).status_code, 403)
        result = self.client.put(self.base + '/settings', json=self.body, headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['settings']['channel_ids'], ['20', '21'])
        self.discord.can_manage.assert_awaited_with('token', 1, use_cache=False)
        self.assertEqual(self.client.put(self.base + '/settings', json=self.body, headers=self.headers).status_code, 409)
        self.discord.can_manage.return_value = False
        self.assertEqual(self.client.get(self.base).status_code, 403)
        self.assertEqual(self.client.get(self.base + '/settings').status_code, 403)

    def test_settings_resource_type_scope_nsfw_and_strict_types(self):
        for changes in ({'channel_ids': ['999']}, {'channel_ids': ['22']}, {'channel_ids': ['23']},
                        {'retention_days': True}, {'track_members': 1}, {'retention_days': 0}):
            body = {**self.body, 'settings': {**self.body['settings'], **changes}}
            response = self.client.put(self.base + '/settings', json=body, headers=self.headers)
            self.assertEqual(response.status_code, 422, response.text)
        self.assertFalse(self.client.get(self.base + '/settings').json()['enabled'])

    def test_report_unknown_is_null_and_other_guild_cannot_expose_aggregates(self):
        self.client.put(self.base + '/settings', json=self.body, headers=self.headers)
        repo = self.context.insights_repository
        repo.claim(1, 'generated')
        repo.event(1, 'generated', 'messages', '100', channel=20)
        response = self.client.get(self.base)
        self.assertEqual(response.status_code, 200, response.text)
        report = response.json()
        self.assertEqual(report['timezone'], 'UTC')
        self.assertTrue(report['collecting'])
        self.assertEqual(report['days'][-1]['messages'], 1)
        self.assertIsNone(report['days'][0]['messages'])
        self.assertNotIn('owner', response.text)
        self.assertNotIn('user_id', response.text)
        foreign = self.client.get('/api/v1/guilds/2/insights').json()
        self.assertTrue(all(not day['observed'] for day in foreign['days']))

    def test_invalid_period_and_off_reading_disable_with_deleted_resource(self):
        self.assertEqual(self.client.get(self.base, params={'start': '2026-02-30'}).status_code, 422)
        self.assertEqual(self.client.get(self.base, params={'start': '2020-01-01', 'end': '2030-01-01'}).status_code, 422)
        response = self.client.put(self.base + '/settings', json=self.body, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.discord.guild_resources.return_value = ([], [], 8)
        disabled = self.client.put(self.base + '/settings', json={**self.body, 'enabled': False, 'revision': 1}, headers=self.headers)
        self.assertEqual(disabled.status_code, 200, disabled.text)
        report = self.client.get(self.base).json()
        self.assertFalse(report['enabled'])
        self.assertFalse(report['collecting'])
