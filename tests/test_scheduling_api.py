"""Schedule APIs enforce manager access, CSRF, fresh resources and revisions."""
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from dashboard.api_v1 import create_api_router
from dashboard.repository import DashboardRepository
from guild_settings import GuildSettingsRepository
from scheduling.repository import ScheduleRepository
from db_support import prepare_database


class SchedulingApiTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.url=prepare_database(Path(temp.name)/'schedule-api',self.addCleanup)
        DashboardRepository(self.url).create_dashboard_session('session','token',3600)
        self.session={'session_id':'session','csrf_token':'csrf'}
        self.discord=SimpleNamespace(current_user=AsyncMock(return_value={'id':'20'}),can_manage=AsyncMock(return_value=True),guild_resources=AsyncMock(return_value=([{'id':'10','type':0}],[],0)))
        app=FastAPI()
        @app.middleware('http')
        async def session(request,next):
            request.scope['session']=self.session
            return await next(request)
        app.include_router(create_api_router(self.url,self.discord))
        self.client=TestClient(app);self.addCleanup(self.client.close)
        self.headers={'x-csrf-token':'csrf'}
        self.settings=GuildSettingsRepository(self.url);self.settings.set_module(1,'scheduled_messages',enabled=True)
        self.base='/api/v1/guilds/1/schedules/items'
        self.body={'request_key':'generated','payload':{'kind':'message','title':'Generated','body':'Test','channel_id':'10','run_at':int(time.time())+600}}

    def create(self):
        response=self.client.post(self.base,json=self.body,headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_authentication_and_csrf_do_not_create_records(self):
        self.assertEqual(self.client.post(self.base,json=self.body).status_code,403)
        self.discord.can_manage.return_value=False
        self.assertEqual(self.client.get(self.base).status_code,403)
        self.assertEqual(self.client.post(self.base,json=self.body,headers=self.headers).status_code,403)
        self.assertEqual(ScheduleRepository(self.url).items(1),[])
        self.session.clear()
        self.assertEqual(self.client.get(self.base).status_code,401)

    def test_create_wire_ids_fresh_resources_replay_and_cancel_revision(self):
        row=self.create()
        self.assertEqual(row['guild_id'],'1');self.assertEqual(row['actor_id'],'20')
        self.assertEqual(row['payload']['channel_id'],'10')
        self.assertNotIn('request_key',row)
        self.assertEqual(self.create()['id'],row['id'])
        self.discord.guild_resources.assert_awaited_with(1,use_cache=False)
        path=self.base+f"/{row['id']}/cancel"
        self.assertEqual(self.client.post(path,json={'revision':9},headers=self.headers).status_code,409)
        self.assertEqual(self.client.post(path,json={'revision':1},headers=self.headers).json()['status'],'cancelled')

    def test_cross_guild_resources_invalid_time_and_disabled(self):
        self.body['payload']['channel_id']='999'
        self.assertEqual(self.client.post(self.base,json=self.body,headers=self.headers).status_code,422)
        self.body['payload']['channel_id']='10';row=self.create()
        self.settings.set_module(2,'scheduled_messages',enabled=True)
        self.assertEqual(self.client.get(f"/api/v1/guilds/2/schedules/items/{row['id']}/history").status_code,404)
        self.settings.set_module(1,'scheduled_messages',enabled=False)
        self.assertEqual(self.client.post(self.base+f"/{row['id']}/cancel",json={'revision':1},headers=self.headers).status_code,403)
        self.assertEqual(self.client.get(self.base).status_code,200)

    def test_edit_conflict_and_write_access_refresh(self):
        row=self.create();path=self.base+f"/{row['id']}"
        value={'payload':{**self.body['payload'],'title':'Changed'},'revision':1}
        self.assertEqual(self.client.put(path,json=value,headers=self.headers).status_code,200)
        self.assertEqual(self.client.put(path,json=value,headers=self.headers).status_code,409)
        self.discord.can_manage.return_value=False
        self.assertEqual(self.client.put(path,json={**value,'revision':2},headers=self.headers).status_code,403)
        self.discord.can_manage.assert_awaited_with('token',1,use_cache=False)
