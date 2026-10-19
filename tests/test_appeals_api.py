"""Private API access, CSRF, independent review and current revision checks."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from dashboard.api_v1 import create_api_router
from dashboard.repository import DashboardRepository
from guild_settings import GuildSettingsRepository
from appeals.repository import AppealRepository
from moderation import ModerationRepository
from db_support import prepare_database


class AppealsApiTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.url=prepare_database(Path(temp.name)/'api',self.addCleanup)
        dashboard=DashboardRepository(self.url);dashboard.create_dashboard_session('session','token',3600)
        self.session={'session_id':'session','csrf_token':'csrf'}
        self.discord=SimpleNamespace(current_user=AsyncMock(return_value={'id':'91'}),can_manage=AsyncMock(return_value=True))
        app=FastAPI()
        @app.middleware('http')
        async def session(request,next):request.scope['session']=self.session;return await next(request)
        app.include_router(create_api_router(self.url,self.discord))
        self.client=TestClient(app);self.addCleanup(self.client.close)
        self.headers={'x-csrf-token':'csrf'}
        self.repo=AppealRepository(self.url)
        self.settings=GuildSettingsRepository(self.url);self.settings.set_module(1,'appeals',enabled=True)
        case_id=ModerationRepository(self.url).add_case(1,10,'warn','test',moderator_id=90)
        self.item=self.repo.open(1,10,100,'Private generated text',case=ModerationRepository(self.url).case(1,case_id))
        self.base=f"/api/v1/guilds/1/appeals/items/{self.item['id']}"

    def test_private_details_and_authentication(self):
        response=self.client.get(self.base)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['messages'][0]['actor_id'],'10')
        self.assertNotIn('interaction_id',response.text)
        self.discord.can_manage.return_value=False
        self.assertEqual(self.client.get(self.base).status_code,403)
        self.session.clear();self.assertEqual(self.client.get(self.base).status_code,401)

    def test_cross_guild_csrf_and_independent_reviewer(self):
        value={'status':'accepted','reason':'Independent review','revision':1}
        self.assertEqual(self.client.post(self.base+'/review',json=value).status_code,403)
        for actor in ('10','90'):
            self.discord.current_user.return_value={'id':actor}
            self.assertEqual(self.client.post(self.base+'/review',json=value,headers=self.headers).status_code,403)
        self.discord.current_user.return_value={'id':'91'}
        self.settings.set_module(2,'appeals',enabled=True)
        self.assertEqual(self.client.post(self.base.replace('/guilds/1/','/guilds/2/')+'/review',json=value,headers=self.headers).status_code,404)
        self.assertEqual(self.client.post(self.base+'/review',json=value,headers=self.headers).status_code,200)
        self.assertEqual(self.client.post(self.base+'/review',json=value,headers=self.headers).status_code,409)

    def test_staff_reply_disabled_and_invalid_ticket_retry(self):
        value={'content':'Generated staff reply','revision':1}
        self.assertEqual(self.client.post(self.base+'/reply',json=value,headers=self.headers).status_code,200)
        self.assertEqual(self.client.post(self.base+'/reply',json=value,headers=self.headers).status_code,409)
        self.assertEqual(self.client.post(self.base+'/ticket',json={'ticket_id':999,'revision':2},headers=self.headers).status_code,403)
        self.assertEqual(self.client.post(self.base+'/delivery/999/retry',json={'revision':2},headers=self.headers).status_code,409)
        self.settings.set_module(1,'appeals',enabled=False)
        self.assertEqual(self.client.post(self.base+'/reply',json={**value,'revision':2},headers=self.headers).status_code,403)

    def test_live_write_authorization_is_not_cached(self):
        self.assertEqual(self.client.get(self.base).status_code,200)
        self.discord.can_manage.return_value=False
        self.assertEqual(self.client.post(self.base+'/reply',json={'content':'not allowed','revision':1},headers=self.headers).status_code,403)
        self.assertEqual(len(self.repo.conversation(1,self.item['id'])['messages']),1)
