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
from starboard.repository import StarboardRepository
from jobs import Outcome
from database import transaction


class StarboardApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.url=prepare_database(Path(self.tmp.name)/'starboard-api',self.addCleanup)
        DashboardRepository(self.url).create_dashboard_session('session','token',3600)
        self.session={'session_id':'session','csrf_token':'csrf'}
        self.discord=SimpleNamespace(can_manage=AsyncMock(return_value=True),current_user=AsyncMock(return_value={'id':'40'}),guild_resources=AsyncMock(return_value=([{'id':'10','type':0},{'id':'20','type':0}],[],8)),guild_channel=AsyncMock(return_value=None),guild_emojis=AsyncMock(return_value=[]))
        app=FastAPI()
        @app.middleware('http')
        async def session(request,next):request.scope['session']=self.session;return await next(request)
        app.include_router(create_api_router(self.url,self.discord));self.client=TestClient(app);self.addCleanup(self.client.close)
        self.headers={'x-csrf-token':'csrf'};self.base='/api/v1/guilds/1/starboard/boards'
        self.settings=GuildSettingsRepository(self.url);self.settings.set_module(1,'starboard',enabled=True,settings={})
        self.repo=StarboardRepository(self.url)
        self.config={'name':'Generated board','enabled':True,'target_channel_id':'20','source_channel_ids':['10']}

    def create(self):
        response=self.client.post(self.base,json={'config':self.config,'request_key':'generated-create'},headers=self.headers)
        self.assertEqual(response.status_code,200,response.text);return response.json()

    def test_create_and_edit_require_csrf_live_authorization_and_revision(self):
        self.assertEqual(self.client.post(self.base,json={'config':self.config,'request_key':'generated-create'}).status_code,403)
        board=self.create();path=self.base+f"/{board['id']}"
        self.assertEqual(board['config']['source_channel_ids'],['10']);self.assertEqual(board['guild_id'],'1')
        edit={'config':{**self.config,'name':'Updated'},'revision':1}
        self.assertEqual(self.client.put(path,json=edit,headers=self.headers).status_code,200)
        self.assertEqual(self.client.put(path,json=edit,headers=self.headers).status_code,409)
        self.discord.can_manage.assert_awaited_with('token',1,use_cache=False)
        self.discord.can_manage.return_value=False
        self.assertEqual(self.client.get(self.base).status_code,403)

    def test_unknown_create_response_can_retry_same_key_without_creating_another_board(self):
        first=self.create();second=self.create()
        self.assertEqual(first['id'],second['id']);self.assertNotIn('request_key',second)
        self.assertEqual(len(self.repo.boards(1)),1)
        response=self.client.post(self.base,json={'config':{**self.config,'name':'Different'},'request_key':'generated-create'},headers=self.headers)
        self.assertEqual(response.status_code,409)

    def test_missing_foreign_resources_and_invalid_input_are_rejected(self):
        for config in ({**self.config,'source_channel_ids':['999']},{**self.config,'emoji':'<:generated:123>'},{**self.config,'threshold':True},{**self.config,'retention_days':0}):
            response=self.client.post(self.base,json={'config':config,'request_key':'generated-invalid'},headers=self.headers)
            self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(self.client.post(self.base,json={},headers=self.headers).status_code,422)
        self.discord.guild_channel.return_value={'id':'11','type':11,'parent_id':'10','nsfw':False}
        response=self.client.post(self.base,json={'config':{**self.config,'source_channel_ids':['11']},'request_key':'generated-thread'},headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        self.discord.guild_channel.assert_awaited_with(1,11)

    def test_off_retains_reading_and_expired_entries_are_hidden(self):
        board=self.create();source={'guild_id':1,'channel_id':10,'message_id':100,'author_id':20,'author_bot':False,'content':'Generated proof'}
        item=self.repo.observe(1,board['id'],1,source,3)
        self.settings.set_module(1,'starboard',enabled=False)
        self.assertEqual(self.client.get(self.base).status_code,200)
        self.assertEqual(self.client.put(self.base+f"/{board['id']}",json={'config':self.config,'revision':1},headers=self.headers).status_code,403)
        entries=self.base+f"/{board['id']}/entries"
        response=self.client.get(entries);self.assertEqual(response.json()['items'][0]['snapshot']['author_id'],'20')
        with transaction(self.url) as c:c.execute('UPDATE starboard_entries SET expires_at=1 WHERE id=%s',(item['id'],))
        self.assertEqual(self.client.get(entries).json()['items'],[])
        self.assertEqual(self.client.get(f"/api/v1/guilds/2/starboard/boards/{board['id']}/entries").status_code,404)

    def test_source_fetch_retry_is_audited_and_csrf_protected(self):
        board=self.create();self.repo.enqueue_refresh(1,10,100);claim=self.repo.refresh_jobs.claim('generated')
        self.repo.refresh_jobs.finish(claim,Outcome('Generated source failure'))
        path=self.base+f"/{board['id']}/source-jobs/{claim.id}/retry"
        self.assertEqual(self.client.post(path,json={'revision':1}).status_code,403)
        response=self.client.post(path,json={'revision':1},headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['source_fetches'][0]['retry_actor_id'],'40')
        self.assertEqual(response.json()['events'][0]['event_type'],'source_retry')

    def test_disabling_can_withdraw_when_old_channel_resources_are_gone(self):
        board=self.create();self.discord.guild_resources.side_effect=RuntimeError('Generated unavailable resource service')
        response=self.client.put(self.base+f"/{board['id']}",json={'config':{**self.config,'enabled':False},'revision':1},headers=self.headers)
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(response.json()['config']['enabled'])
