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

    def test_rescheduling_rejects_a_start_after_the_saved_deadline(self):
        import time
        now=int(time.time());day=86400
        for explicit_deadline in (False,True):
            with self.subTest(explicit_deadline=explicit_deadline):
                self.body.update(request_key=f'reschedule-{explicit_deadline}',scheduled_at=now+day,closes_at=now+2*day)
                poll=self.create()
                path=f"{self.base}/{poll['id']}"
                body={'revision':poll['revision'],'config':poll['config'],'scheduled_at':now+3*day}
                if explicit_deadline:body['closes_at']=poll['closes_at']
                response=self.client.put(path,json=body,headers=self.headers)
                self.assertEqual(response.status_code,422,response.text)
                saved=self.client.get(path).json()
                for field in ('scheduled_at','closes_at','revision','status'):
                    self.assertEqual(saved[field],poll[field])
                body['scheduled_at']=now+day+3600
                response=self.client.put(path,json=body,headers=self.headers)
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()['closes_at'],poll['closes_at'])

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
        self.repo.vote(1,poll['id'],999,[0],revision=poll['revision'])
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

    def role_resources(self):
        import asyncio
        import httpx
        from dashboard.discord_api import DiscordAPI
        roles=[{'id':str(id),'name':name,'position':position,'permissions':str(permissions),'managed':managed}
               for id,name,position,permissions,managed in ((1,'@everyone',0,0,False),(2,'Bot',10,8,True),
                   (3,'Member',1,0,False),(4,'Administrator',2,8,False),(5,'Higher',20,0,False),(6,'Managed',1,0,True))]
        def transport(request):
            if request.url.path.endswith('/roles'):payload=roles
            elif request.url.path.endswith('/channels'):payload=[{'id':'10','name':'polls','type':0}]
            elif request.url.path.endswith('/members/2'):payload={'roles':['2']}
            else:raise AssertionError(str(request.url))
            return httpx.Response(200,json=payload)
        api=DiscordAPI('offline','2','offline','http://testserver/callback')
        api._client=httpx.AsyncClient(transport=httpx.MockTransport(transport))
        self.addCleanup(lambda:asyncio.run(api.close()))
        self.discord.guild_resources=api.guild_resources
        return roles

    def test_reference_role_matrix_across_poll_operations(self):
        roles=self.role_resources()
        result=self.client.get('/api/v1/guilds/1/polls/resources')
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual({row['id'] for row in result.json()['roles']},{row['id'] for row in roles})
        for role in roles:
            with self.subTest(role=role['name']):
                self.body['request_key']='role-'+role['id']
                self.body['config'].update(allowed_roles=[role['id']],denied_roles=[role['id']])
                poll=self.create()
                path=f"{self.base}/{poll['id']}"
                response=self.client.put(path,json={'revision':poll['revision'],'config':poll['config']},headers=self.headers)
                self.assertEqual(response.status_code,200,response.text)
                response=self.client.post(path+'/actions',json={'revision':response.json()['revision'],'action':'launch'},headers=self.headers)
                self.assertEqual(response.status_code,200,response.text)
        path='/api/v1/guilds/1/polls/settings'
        row=self.client.get(path).json()
        row['settings'].update(role_weights={role['id']:10 for role in roles},role_permissions={role['id']:['view'] for role in roles})
        response=self.client.put(path,json=row,headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        # Promotion must not invalidate an unrelated save of existing references.
        roles[2].update(position=100,permissions='8',managed=True)
        row=response.json();row['settings']['retention_days']=91
        response=self.client.put(path,json=row,headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)

    def test_everyone_delegation_uses_implicit_guild_membership_role(self):
        self.discord.can_manage.return_value=False
        self.repo.settings.set_module(1,'advanced_polls',enabled=True,settings={'role_permissions':{'1':['view']}})
        self.assertEqual(self.client.get(self.base).status_code,200)
        result=self.client.get('/api/v1/guilds').json()['items']
        self.assertEqual(result[0]['feature_ids'],['advanced_polls'])

    def test_foreign_roles_are_rejected_across_reference_fields(self):
        from copy import deepcopy
        poll=self.create()
        for field in ('allowed_roles','denied_roles'):
            with self.subTest(field=field):
                config=deepcopy(poll['config']);config[field]=['999']
                body={**self.body,'request_key':'foreign-'+field,'config':config}
                self.assertEqual(self.client.post(self.base,json=body,headers=self.headers).status_code,422)
                response=self.client.put(f"{self.base}/{poll['id']}",json={'revision':poll['revision'],'config':config},headers=self.headers)
                self.assertEqual(response.status_code,422,response.text)
                foreign=self.repo.create(1,10,20,config,'foreign-launch-'+field)
                response=self.client.post(f"{self.base}/{foreign['id']}/actions",json={'revision':foreign['revision'],'action':'launch'},headers=self.headers)
                self.assertEqual(response.status_code,422,response.text)
        path='/api/v1/guilds/1/polls/settings'
        for field,value in (('role_weights',10),('role_permissions',['view'])):
            with self.subTest(field=field):
                row=self.client.get(path).json();row['settings'][field]={'999':value}
                response=self.client.put(path,json=row,headers=self.headers)
                self.assertEqual(response.status_code,422,response.text)
                self.assertEqual(self.client.get(path).json()['revision'],row['revision'])

    def test_delegated_workspace_is_discovered_and_lost_with_membership(self):
        self.discord.can_manage.return_value=False
        self.repo.settings.set_module(1,'advanced_polls',enabled=True,settings={'role_permissions':{'3':['manage']}})
        result=self.client.get('/api/v1/guilds')
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['items'][0]['access'],'delegated')
        self.assertEqual(result.json()['items'][0]['feature_ids'],['advanced_polls'])
        self.discord.guild_member.return_value=None
        self.assertEqual(self.client.get('/api/v1/guilds').json()['items'],[])

