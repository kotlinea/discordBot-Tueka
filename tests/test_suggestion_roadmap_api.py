"""Manager-only roadmap labels, merge preview, conflict and expiry boundaries."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from db_support import prepare_database
from dashboard.api_v1 import create_api_router
from dashboard.repository import DashboardRepository
from guild_settings import GuildSettingsRepository
from suggestions import SuggestionRepository
from database import transaction


class RoadmapApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.url=prepare_database(Path(self.tmp.name)/'roadmap-api',self.addCleanup)
        DashboardRepository(self.url).create_dashboard_session('session','token',3600)
        self.session={'session_id':'session','csrf_token':'csrf'}
        self.discord=SimpleNamespace(can_manage=AsyncMock(return_value=True),current_user=AsyncMock(return_value={'id':'40'}))
        app=FastAPI()
        @app.middleware('http')
        async def session(request,next):request.scope['session']=self.session;return await next(request)
        app.include_router(create_api_router(self.url,self.discord))
        self.client=TestClient(app);self.addCleanup(self.client.close)
        self.headers={'x-csrf-token':'csrf'}
        self.settings=GuildSettingsRepository(self.url)
        self.settings.set_module(1,'suggestions',enabled=True,settings={'categories':['改善'],'tags':['UI']})
        self.repo=SuggestionRepository(self.url)
        self.source=self.repo.create(1,10,20,{'idea':'Generated duplicate'})
        self.target=self.repo.create(1,10,21,{'idea':'Generated canonical'})
        self.base=f"/api/v1/guilds/1/suggestions/items/{self.source['id']}"

    def test_labels_validate_taxonomy_revision_csrf_and_filters(self):
        value={'category':'改善','tags':['UI'],'revision':1}
        self.assertEqual(self.client.post(self.base+'/labels',json=value).status_code,403)
        response=self.client.post(self.base+'/labels',json=value,headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['tags'],['UI'])
        self.assertEqual(self.client.post(self.base+'/labels',json=value,headers=self.headers).status_code,409)
        items=self.client.get('/api/v1/guilds/1/suggestions/items?category=改善&tag=UI').json()['items']
        self.assertEqual([item['id'] for item in items],[self.source['id']])
        self.assertEqual(self.client.get('/api/v1/guilds/1/suggestions/items?status=unknown').status_code,422)

    def test_merge_preview_and_target_revision_are_required_and_history_is_kept(self):
        detail=self.client.get(self.base)
        self.assertEqual(detail.status_code,200,detail.text)
        self.assertEqual(detail.json()['guild_id'],'1')
        value={'target_id':self.target['id'],'target_revision':9,'revision':1,'reason':'Generated duplicate reason'}
        self.assertEqual(self.client.post(self.base+'/merge',json=value,headers=self.headers).status_code,409)
        value['target_revision']=1
        response=self.client.post(self.base+'/merge',json=value,headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['merged_into'],self.target['id'])
        self.assertEqual(response.json()['status'],'merged')
        events=self.client.get(self.base+'/events').json()['items']
        self.assertEqual(events[0]['detail']['reason'],'Generated duplicate reason')

    def test_cross_guild_disable_expiry_and_live_permissions(self):
        foreign=self.repo.create(2,10,20,{'idea':'Foreign'})
        value={'target_id':foreign['id'],'target_revision':1,'revision':1,'reason':'Cross Guild'}
        self.assertEqual(self.client.post(self.base+'/merge',json=value,headers=self.headers).status_code,404)
        self.settings.set_module(1,'suggestions',enabled=False)
        self.assertEqual(self.client.post(self.base+'/labels',json={'revision':1},headers=self.headers).status_code,403)
        self.assertEqual(self.client.get(self.base).status_code,200)
        self.discord.can_manage.return_value=False
        self.assertEqual(self.client.get(self.base).status_code,403)
        self.assertEqual(self.client.post(self.base+'/labels',json={'revision':1},headers=self.headers).status_code,403)
        self.discord.can_manage.assert_awaited_with('token',1,use_cache=False)
        self.discord.can_manage.return_value=True
        with transaction(self.url) as c:c.execute('UPDATE suggestions SET expires_at=1 WHERE id=%s',(self.source['id'],))
        self.assertEqual(self.client.get(self.base).status_code,404)
