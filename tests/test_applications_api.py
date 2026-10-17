"""HTTP authorization, CSRF, resource ownership and private review contracts."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from dashboard.api_v1 import create_api_router
from dashboard.repository import DashboardRepository
from dashboard.discord_api import ADMINISTRATOR
from applications.repository import ApplicationRepository
from guild_settings import GuildSettingsRepository
from db_support import prepare_database
from test_applications import definition


class ApplicationsApiTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.url=prepare_database(Path(temp.name)/'api',self.addCleanup)
        dashboard=DashboardRepository(self.url)
        dashboard.create_dashboard_session('session','token',3600)
        self.session={'session_id':'session','csrf_token':'csrf'}
        self.discord=SimpleNamespace(current_user=AsyncMock(return_value={'id':'900'}),can_manage=AsyncMock(return_value=True),guild_resources=AsyncMock(return_value=([],[{'id':'20'}],ADMINISTRATOR)))
        app=FastAPI()
        @app.middleware('http')
        async def session(request,call_next):
            request.scope['session']=self.session
            return await call_next(request)
        app.include_router(create_api_router(self.url,self.discord))
        self.client=TestClient(app);self.addCleanup(self.client.close)
        self.headers={'x-csrf-token':'csrf'}
        self.base='/api/v1/guilds/1/applications'
        self.repo=ApplicationRepository(self.url)
        GuildSettingsRepository(self.url).set_module(1,'applications',enabled=True)

    def test_form_create_edit_revision_and_foreign_roles(self):
        r=self.client.post(self.base+'/forms',json=definition(required_role_ids=['20']),headers=self.headers)
        self.assertEqual(r.status_code,200,r.text)
        item=r.json();self.assertEqual(item['required_role_ids'],['20'])
        path=self.base+f"/forms/{item['id']}"
        self.assertEqual(self.client.put(path,json=definition(),headers=self.headers).status_code,422)
        self.assertEqual(self.client.put(path,json={**definition(), 'revision':2},headers=self.headers).status_code,409)
        self.assertEqual(self.client.put(path,json={**definition(), 'revision':1,'denied_role_ids':['999']},headers=self.headers).status_code,422)
        self.assertEqual(self.client.put(path,json={**definition(), 'revision':1},headers=self.headers).status_code,200)
        self.assertEqual(self.client.put(path.replace('/guilds/1/','/guilds/2/'),json={**definition(),'revision':2},headers=self.headers).status_code,404)

    def test_csrf_session_and_guild_manage_access(self):
        path=self.base+'/forms'
        self.assertEqual(self.client.post(path,json=definition()).status_code,403)
        self.discord.can_manage.return_value=False
        for route in ('/forms','/items'):
            self.assertEqual(self.client.get(self.base+route).status_code,403)
        self.assertEqual(self.client.post(path,json=definition(),headers=self.headers).status_code,403)
        self.session.clear()
        self.assertEqual(self.client.get(path).status_code,401)
        self.assertEqual(self.repo.forms(1),[])

    def seed(self):
        form=self.repo.save_form(1,900,definition())
        return self.repo.submit(1,form['id'],10,100,{'why':'Private generated answer'},revision=1,roles=[],created_at=1,joined_at=1)

    def test_private_answers_ids_and_review_event(self):
        item=self.seed()
        response=self.client.get(self.base+'/items')
        self.assertEqual(response.status_code,200,response.text)
        value=response.json()['items'][0]
        self.assertEqual(value['author_id'],'10')
        self.assertNotIn('interaction_id',value)
        path=self.base+f"/items/{item['id']}"
        body={'status':'approved','reason':'Accepted','revision':1}
        self.assertEqual(self.client.post(path+'/review',json=body).status_code,403)
        self.assertEqual(self.client.post(path+'/review',json={**body,'reason':' '},headers=self.headers).status_code,422)
        response=self.client.post(path+'/review',json=body,headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['status'],'approved')
        self.assertEqual(self.client.post(path+'/review',json=body,headers=self.headers).status_code,409)
        events=self.client.get(path+'/events').json()['items']
        self.assertEqual(events[0]['actor_id'],'900')
        self.assertEqual(events[0]['reason'],'Accepted')
        self.assertEqual(self.client.get(path.replace('/guilds/1/','/guilds/2/')+'/events').status_code,404)
        self.discord.can_manage.return_value=False
        self.assertEqual(self.client.get(path+'/events').status_code,403)

    def test_disabled_and_self_review_are_refused(self):
        item=self.seed();path=self.base+f"/items/{item['id']}/review"
        body={'status':'approved','reason':'Accepted','revision':1}
        self.discord.current_user.return_value={'id':'10'}
        self.assertEqual(self.client.post(path,json=body,headers=self.headers).status_code,403)
        self.discord.current_user.return_value={'id':'900'}
        GuildSettingsRepository(self.url).set_module(1,'applications',enabled=False)
        self.assertEqual(self.client.post(path,json=body,headers=self.headers).status_code,403)
        self.assertEqual(len(self.repo.events(1,item['id'])),1)
