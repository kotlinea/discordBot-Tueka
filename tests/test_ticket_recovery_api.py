import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.api_v1 import create_api_router
from dashboard.discord_api import ADMINISTRATOR
from dashboard.repository import DashboardRepository
from db_support import prepare_database
from ticketing import TicketRepository


class TicketRecoveryApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        database = prepare_database(root / 'api.db')
        settings = SimpleNamespace(database_path=database, data_dir=root,
            ticket_encryption_key=Fernet.generate_key().decode(), reaction_role_max_mappings_per_message=20,
            **{f'ticket_s3_{key}': '' for key in ('endpoint_url', 'region', 'bucket', 'access_key_id', 'secret_access_key', 'prefix')})
        DashboardRepository(database).create_dashboard_session('session', 'token', 3600)
        self.repo = TicketRepository(database)
        team = self.repo.save_team(1, {'name': 'Staff', 'role_ids': [500]})
        self.bundle = self.repo.save_panel_bundle(1, {
            'panel': {'name': 'Support', 'mode': 'channel', 'category_id': 100, 'team_id': team['id']},
            'deployment': {'name': 'Entry', 'channel_id': 10, 'title': 'Support'}})
        self.repo.claim_panel_messages('worker')
        discord = SimpleNamespace(can_manage=AsyncMock(return_value=True),
            current_user=AsyncMock(return_value={'id': '20'}),
            guild_resources=AsyncMock(return_value=([
                {'id': '10', 'type': 0}, {'id': '11', 'type': 0}, {'id': '100', 'type': 4}], [{'id': '500'}], ADMINISTRATOR)))
        app = FastAPI()
        @app.middleware('http')
        async def session(request, call_next):
            request.scope['session'] = {'session_id': 'session', 'csrf_token': 'csrf'}
            return await call_next(request)
        app.include_router(create_api_router(database, discord, settings))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_move_during_unknown_delivery_returns_recovery_conflict_without_mutation(self):
        panel_id = self.bundle['panel']['id']
        before = self.repo.panel_bundle(1, panel_id)
        payload = {'panel': before['panel'], 'deployment': {
            **before['deployment'], 'panel_message_id': before['deployment']['id'], 'channel_id': 11}}
        response = self.client.put(f'/api/v1/guilds/1/tickets/panels/{panel_id}/bundle',
            json=payload, headers={'x-csrf-token': 'csrf'})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()['detail']['code'], 'panel_recovery_required')
        self.assertEqual(self.repo.panel_bundle(1, panel_id), before)
