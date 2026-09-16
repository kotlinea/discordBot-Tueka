"""Isolated API application with explicit fake Discord and session boundaries."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.api_v1 import create_api_router
from dashboard.discord_api import ADMINISTRATOR, PERMISSION_BITS
from dashboard.repository import DashboardRepository
from db_support import prepare_database


class ApiFixture:
    def __init__(self, root: Path):
        self.database = prepare_database(root / 'api.db')
        self.settings = SimpleNamespace(database_path=self.database, data_dir=root,
            ticket_encryption_key=Fernet.generate_key().decode(), reaction_role_max_mappings_per_message=20,
            twitch_client_id='', twitch_client_secret='', dashboard_base_url='', social_webhook_secret='',
            x_bearer_token='', instagram_rss_url_template='', social_max_subscriptions_per_provider=10,
            **{f'ticket_s3_{key}': '' for key in ('endpoint_url', 'region', 'bucket', 'access_key_id', 'secret_access_key', 'prefix')})
        DashboardRepository(self.database).create_dashboard_session('session', 'token', 3600)
        self.session = {'session_id': 'session', 'csrf_token': 'csrf'}
        permissions = ADMINISTRATOR | sum(PERMISSION_BITS.values())
        self.discord = SimpleNamespace(
            can_manage=AsyncMock(return_value=True), current_user=AsyncMock(return_value={'id': '20', 'username': 'Member'}),
            guild_resources=AsyncMock(return_value=([
                {'id': '10', 'type': 0, 'name': 'support', 'bot_permissions': str(permissions)},
                {'id': '100', 'type': 4, 'name': 'category', 'bot_permissions': str(permissions)}],
                [{'id': '500', 'name': 'staff'}], permissions)),
            guild_emojis=AsyncMock(return_value=[]), guild_member=AsyncMock(return_value={'roles': ['500']}),
            user_guilds=AsyncMock(return_value=[{'id': '1', 'name': 'Guild', 'permissions': str(ADMINISTRATOR)}]),
            bot_guild_ids=AsyncMock(return_value={1}), channel_message=AsyncMock(return_value={'id': '900'}),
        )
        self.app = FastAPI()

        @self.app.middleware('http')
        async def session(request, call_next):
            request.scope['session'] = self.session
            return await call_next(request)

        self.app.include_router(create_api_router(self.database, self.discord, self.settings))
        self.client = TestClient(self.app)

    @property
    def headers(self):
        return {'x-csrf-token': 'csrf'}
