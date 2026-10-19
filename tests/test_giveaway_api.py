import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from db_support import prepare_database
from dashboard.api.context import create_context
from dashboard.api.engagement.giveaways import create_router
from dashboard.repository import DashboardRepository
from guild_settings import GuildSettingsRepository


class GiveawayApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.url = prepare_database(Path(self.tmp.name) / 'giveaway-api', self.addCleanup)
        DashboardRepository(self.url).create_dashboard_session('session', 'token', 3600)
        self.session = {'session_id': 'session', 'csrf_token': 'csrf'}
        self.discord = SimpleNamespace(can_manage=AsyncMock(return_value=True), current_user=AsyncMock(return_value={'id': '40'}),
                                       guild_resources=AsyncMock(return_value=([{'id': '20', 'type': 0}], [{'id': '30'}], 8)))
        self.context = create_context(self.url, self.discord)
        app = FastAPI()
        @app.middleware('http')
        async def session(request, next):
            request.scope['session'] = self.session
            return await next(request)
        app.include_router(create_router(self.context), prefix='/api/v1')
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.base = '/api/v1/guilds/1/giveaways'
        self.headers = {'x-csrf-token': 'csrf'}
        self.config = {'title': 'Generated campaign', 'channel_id': '20', 'ends_at': int(time.time()) + 600}
        self.settings = GuildSettingsRepository(self.url)
        self.settings.set_module(1, 'giveaways', enabled=True)

    def create(self):
        response = self.client.post(self.base, json={'config': self.config, 'request_key': 'generated'}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_csrf_live_management_and_draft_revision_guards(self):
        self.assertEqual(self.client.post(self.base, json={'config': self.config, 'request_key': 'generated'}).status_code, 403)
        item = self.create()
        self.assertEqual(item['guild_id'], '1')
        self.assertNotIn('request_key', item)
        path = self.base + f'/{item["id"]}'
        body = {'revision': item['revision'], 'config': {**self.config, 'title': 'Updated'}}
        self.assertEqual(self.client.put(path, json=body, headers=self.headers).status_code, 200)
        self.assertEqual(self.client.put(path, json=body, headers=self.headers).status_code, 409)
        self.discord.can_manage.assert_awaited_with('token', 1, use_cache=False)
        self.discord.can_manage.return_value = False
        self.assertEqual(self.client.get(path).status_code, 403)

    def test_resource_scope_strict_types_and_idempotent_creation(self):
        first = self.create()
        self.assertEqual(self.create()['id'], first['id'])
        for change in ({'channel_id': '999'}, {'required_role_ids': ['999']}, {'winner_count': True}, {'capacity': 0}, {'retention_days': 0}):
            response = self.client.post(self.base, json={'config': {**self.config, **change}, 'request_key': 'invalid'}, headers=self.headers)
            self.assertEqual(response.status_code, 422, response.text)
        foreign = self.client.get(f'/api/v1/guilds/2/giveaways/{first["id"]}')
        self.assertEqual(foreign.status_code, 404)

    def test_uncertain_creation_can_reconcile_after_deadline_without_new_mutation(self):
        first = self.create()
        self.discord.guild_resources.reset_mock()
        with patch('dashboard.api.engagement.giveaways.time.time', return_value=self.config['ends_at'] + 1):
            second = self.create()
        self.assertEqual(first['id'], second['id'])
        self.discord.guild_resources.assert_not_awaited()

    def test_launch_cancel_and_off_reading_are_audited_without_automatic_deletion(self):
        item = self.create()
        path = self.base + f'/{item["id"]}'
        opened = self.client.post(path + '/launch', json={'revision': item['revision']}, headers=self.headers)
        self.assertEqual(opened.status_code, 200, opened.text)
        changed = self.client.put(path, json={'revision': opened.json()['revision'], 'config': self.config}, headers=self.headers)
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(self.client.post(path + '/cancel', json={'revision': opened.json()['revision'], 'reason': ' '}, headers=self.headers).status_code, 422)
        cancelled = self.client.post(path + '/cancel', json={'revision': opened.json()['revision'], 'reason': 'Generated cancellation'}, headers=self.headers)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        history = self.client.get(path + '/history').json()
        self.assertIn('cancelled', [event['event_type'] for event in history['events']])
        self.assertTrue(all('lease_token' not in job for job in history['draw_jobs']))
        self.settings.set_module(1, 'giveaways', enabled=False)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.post(path + '/reroll', json={'revision': cancelled.json()['revision'], 'reason': 'Generated'}, headers=self.headers).status_code, 403)
