from dashboard.repository import DashboardRepository
from db_support import prepare_database
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.api_v1 import create_api_router
from dashboard.discord_api import ADMINISTRATOR
from guild_settings import GuildSettingsRepository


class SuggestionsApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage = GuildSettingsRepository(prepare_database(Path(self.temp.name) / 'test.db', self.addCleanup))
        self.dashboard_repository = DashboardRepository(self.storage.database_url)
        self.dashboard_repository.create_dashboard_session('test-session', 'test-token', 3600)
        self.session = {'session_id': 'test-session', 'csrf_token': 'test-csrf'}
        self.discord = SimpleNamespace(
            can_manage=AsyncMock(return_value=True),
            guild_resources=AsyncMock(return_value=([{'id': '10', 'type': 0}], [{'id': '20'}], ADMINISTRATOR)),
        )
        app = FastAPI()
        @app.middleware('http')
        async def session(request, call_next):
            request.scope['session'] = self.session
            return await call_next(request)
        app.include_router(create_api_router(self.storage.database_url, self.discord))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.url = '/api/v1/guilds/1/suggestions/settings'

    def payload(self):
        return {'revision': 0, 'enabled': True, 'settings': {'channel_id': '10', 'review_role_ids': ['20']}}

    def save(self, value):
        return self.client.put(self.url, json=value, headers={'x-csrf-token': 'test-csrf'})

    def test_save_read_and_revision_conflict(self):
        first = self.save(self.payload())
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()['settings']['channel_id'], '10')
        self.assertEqual(self.client.get(self.url).json(), first.json())
        self.assertEqual(self.save(self.payload()).status_code, 409)
        self.assertEqual(self.client.get(self.url).json(), first.json())

    def test_missing_revision_is_rejected(self):
        value = self.payload()
        del value['revision']
        self.assertEqual(self.save(value).status_code, 422)
        self.assertEqual(self.storage.get_module(1, 'suggestions')['revision'], 0)

    def test_missing_and_empty_csrf_are_rejected(self):
        self.assertEqual(self.client.put(self.url, json=self.payload()).status_code, 403)
        self.session.pop('csrf_token')
        self.assertEqual(self.client.put(self.url, json=self.payload()).status_code, 403)

    def test_authentication_and_guild_authorization(self):
        self.discord.can_manage.return_value = False
        self.assertEqual(self.save(self.payload()).status_code, 403)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.session.clear()
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_foreign_resources_are_rejected_without_saving(self):
        for key, value in [('channel_id', '99'), ('log_channel_id', '99'), ('review_role_ids', ['99'])]:
            with self.subTest(key=key):
                payload = self.payload()
                payload['settings'][key] = value
                self.assertEqual(self.save(payload).status_code, 422)
        self.assertEqual(self.storage.get_module(1, 'suggestions')['revision'], 0)

    def test_disable_without_channel_or_bot_permissions(self):
        self.discord.guild_resources.return_value = ([], [], 0)
        value = {'revision': 0, 'enabled': False, 'settings': {}}
        result = self.save(value)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertFalse(result.json()['enabled'])
        value.update(revision=1, enabled=True)
        self.assertEqual(self.save(value).status_code, 422)

    def test_audit_member_category_requires_permission_in_v2_api(self):
        from dashboard.discord_api import PERMISSION_BITS
        from features.registry import get_feature
        permissions = sum(PERMISSION_BITS[name] for name in get_feature('audit_log').required_bot_permissions)
        self.discord.guild_resources.return_value = ([{'id': '10', 'type': 0}], [], permissions)
        self.url = '/api/v1/guilds/1/modules/audit_log'
        payload = {'enabled': True, 'revision': 0, 'settings': {'management_channel_id': '10', 'log_member': True}}
        self.assertEqual(self.save(payload).status_code, 422)
        self.assertFalse(self.storage.module_enabled(1, 'audit_log'))
        self.discord.guild_resources.return_value = ([{'id': '10', 'type': 0}], [], permissions | PERMISSION_BITS['view_audit_log'])
        self.assertEqual(self.save(payload).status_code, 200)
