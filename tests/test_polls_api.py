"""AP-WEB/PRIVACY: live authorization, CSRF and filtered wire results."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from database.testing import temporary_database
from dashboard.api_v1 import create_api_router
from dashboard.repository import DashboardRepository
from poll_support import PublishedPollRepository as PollRepository


class PollApiTests(unittest.TestCase):
    def setUp(self):
        ctx=temporary_database();self.url=ctx.__enter__();self.addCleanup(ctx.__exit__,None,None,None)
        DashboardRepository(self.url).create_dashboard_session('session','token',3600)
        self.session={'session_id':'session','csrf_token':'csrf'}
        self.discord=NS(current_user=AsyncMock(return_value={'id':'20'}),guild_member=AsyncMock(return_value={'roles':['3']}),
                        can_manage=AsyncMock(return_value=True),user_guilds=AsyncMock(return_value=[{'id':'1','name':'Poll guild','permissions':'0'}]),
                        guild_resources=AsyncMock(return_value=([{'id':'10','name':'polls','type':0}],[{'id':'3','name':'staff'}],0)),bot_guild_ids=AsyncMock(return_value={1}))
        app=FastAPI()
        @app.middleware('http')
        async def session(request,next):request.scope['session']=self.session;return await next(request)
        app.include_router(create_api_router(self.url,self.discord))
        self.client=TestClient(app);self.addCleanup(self.client.close)
        self.headers={'x-csrf-token':'csrf'}
        self.repo=PollRepository(self.url);self.repo.settings.set_module(1,'advanced_polls',enabled=True)
        self.base='/api/v1/guilds/1/polls/items'
        self.body={'request_key':'new','channel_id':'10','config':{'question':'Q','options':['A','B']}}

    def create(self):
        response=self.client.post(self.base,json=self.body,headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_create_and_revision(self):
        poll=self.create();self.assertEqual(poll['guild_id'],'1')
        self.assertEqual(self.create()['id'],poll['id'])
        response=self.client.put(f"{self.base}/{poll['id']}",json={'revision':1,'config':self.body['config']},headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.put(f"{self.base}/{poll['id']}",json={'revision':1,'config':self.body['config']},headers=self.headers).status_code,409)

    def test_auth_csrf_and_cross_guild(self):
        self.assertEqual(self.client.post(self.base,json=self.body).status_code,403)
        poll=self.create()
        self.assertEqual(self.client.get(f"/api/v1/guilds/2/polls/items/{poll['id']}").status_code,404)
        self.discord.guild_member.return_value=None
        self.assertEqual(self.client.get(self.base).status_code,403)
        self.session.clear();self.assertEqual(self.client.get(self.base).status_code,401)

    def test_anonymous_admin_cannot_export_person(self):
        self.repo.legacy_create(100,1,10,20,'Q',['A','B'],None,None)
        poll=self.repo.by_message(100)
        self.repo.vote(1,poll['id'],999,[0])
        result=self.client.get(f"{self.base}/{poll['id']}")
        self.assertEqual(result.status_code,200,result.text)
        self.assertNotIn('ballots',result.json());self.assertNotIn('participants',result.json())
        exported=self.client.get(f"{self.base}/{poll['id']}/export?format=json")
        self.assertNotIn('999',exported.text)
        self.assertEqual(exported.headers['cache-control'],'no-store')

    def test_delegated_weights_cannot_assign_permissions(self):
        self.discord.can_manage.return_value=False
        self.repo.settings.set_module(1,'advanced_polls',enabled=True,settings={'role_permissions':{'3':['view','weights']}})
        self.assertEqual(self.client.get(self.base).status_code,200)
        self.assertEqual(self.client.post(self.base,json=self.body,headers=self.headers).status_code,403)
        path='/api/v1/guilds/1/polls/settings'
        row=self.client.get(path).json()
        row['settings']['role_permissions']['3'].append('manage')
        self.assertEqual(self.client.put(path,json=row,headers=self.headers).status_code,403)
        row=self.client.get(path).json();row['settings']['role_weights']={'3':10}
        self.assertEqual(self.client.put(path,json=row,headers=self.headers).status_code,200)

    def test_view_only_role_cannot_advance_settings_revision_with_noop(self):
        self.discord.can_manage.return_value=False
        self.repo.settings.set_module(1,'advanced_polls',enabled=True,settings={'role_permissions':{'3':['view']}})
        path='/api/v1/guilds/1/polls/settings'
        row=self.client.get(path).json()
        self.assertEqual(self.client.put(path,json=row,headers=self.headers).status_code,403)
        self.assertEqual(self.client.get(path).json()['revision'],row['revision'])

    def test_resources_and_nulls(self):
        self.body['channel_id']='999'
        self.assertEqual(self.client.post(self.base,json=self.body,headers=self.headers).status_code,422)
        self.body['channel_id']='10';self.body['config']['emojis']=None
        self.assertEqual(self.client.post(self.base,json=self.body,headers=self.headers).status_code,422)

    def test_delegated_workspace_is_discovered_and_lost_with_membership(self):
        self.discord.can_manage.return_value=False
        self.repo.settings.set_module(1,'advanced_polls',enabled=True,settings={'role_permissions':{'3':['manage']}})
        result=self.client.get('/api/v1/guilds')
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['items'][0]['access'],'delegated')
        self.assertEqual(result.json()['items'][0]['feature_ids'],['advanced_polls'])
        self.discord.guild_member.return_value=None
        self.assertEqual(self.client.get('/api/v1/guilds').json()['items'],[])

