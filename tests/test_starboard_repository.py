import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from db_support import prepare_database
from database import transaction
from starboard.repository import StarboardRepository
from jobs import Outcome


class StarboardRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.url=prepare_database(Path(self.tmp.name)/'starboard',self.addCleanup)
        self.now=1000
        self.repo=StarboardRepository(self.url,clock=lambda:self.now)
        self.repo.settings.set_module(1,'starboard',enabled=True,settings={})
        self.config={'name':'Generated','enabled':True,'target_channel_id':20,'source_channel_ids':[10],'threshold':2,'retention_days':1}
        self.board=self.repo.save_board(1,30,self.config)
        self.source={'guild_id':1,'channel_id':10,'message_id':100,'author_id':40,'author_bot':False,'content':'Generated proof'}

    def test_below_threshold_is_not_stored_and_duplicate_events_are_coalesced(self):
        self.assertIsNone(self.repo.observe(1,self.board['id'],1,self.source,1))
        first=self.repo.observe(1,self.board['id'],1,self.source,2)
        again=self.repo.observe(1,self.board['id'],1,self.source,2)
        self.assertEqual(first['revision'],again['revision'])
        self.repo.observe(1,self.board['id'],1,{**self.source,'content':'Edited proof'},3)
        with transaction(self.url) as c:self.assertEqual(c.execute('SELECT count(*) AS n FROM starboard_outbox').fetchone()['n'],1)
        row=self.repo.entries(1,self.board['id'])[0]
        self.assertEqual(row['snapshot']['content'],'Edited proof');self.assertEqual(row['score'],3)

    def test_parallel_board_create_retries_are_idempotent_and_actor_bound(self):
        with ThreadPoolExecutor(4) as pool:
            rows=list(pool.map(lambda _:self.repo.save_board(1,30,self.config,request_key='generated-key'),range(4)))
        self.assertEqual(len({row['id'] for row in rows}),1)
        with self.assertRaises(RuntimeError):self.repo.save_board(1,40,self.config,request_key='generated-key')
        self.assertEqual(len(self.repo.boards(1)),2)

    def test_parallel_observations_have_one_source_record_and_one_pending_job(self):
        with ThreadPoolExecutor(4) as pool:
            rows=list(pool.map(lambda _:self.repo.observe(1,self.board['id'],1,self.source,2),range(4)))
        self.assertEqual(len({r['id'] for r in rows}),1)
        with transaction(self.url) as c:self.assertEqual(c.execute('SELECT count(*) AS n FROM starboard_outbox').fetchone()['n'],1)

    def test_stale_board_cross_guild_and_module_off_cannot_change_records(self):
        with self.assertRaises(RuntimeError):self.repo.observe(1,self.board['id'],2,self.source,2)
        with self.assertRaises(PermissionError):self.repo.observe(1,self.board['id'],1,{**self.source,'guild_id':2},2)
        with self.assertRaises(LookupError):self.repo.board(2,self.board['id'])
        with patch.object(self.repo.settings,'get_module',return_value={'enabled':False}):
            with self.assertRaises(PermissionError):self.repo.observe(1,self.board['id'],1,self.source,2)

    def test_board_update_keeps_original_expiry_and_queues_routing_reconciliation(self):
        item=self.repo.observe(1,self.board['id'],1,self.source,2)
        changed=self.repo.save_board(1,30,{**self.config,'target_channel_id':21,'retention_days':30},board=self.board['id'],revision=1)
        self.assertEqual(changed['revision'],2)
        self.assertEqual(self.repo.entries(1,self.board['id'])[0]['expires_at'],item['expires_at'])
        with self.assertRaises(RuntimeError):self.repo.save_board(1,30,self.config,board=self.board['id'],revision=1)
        self.assertEqual(self.repo.history(1,self.board['id'])[0]['event_type'],'board_updated')

    def test_failed_audit_rolls_back_source_and_job(self):
        with patch.object(self.repo,'_audit',side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):self.repo.observe(1,self.board['id'],1,self.source,2)
        self.assertEqual(self.repo.entries(1,self.board['id']),[])
        with transaction(self.url) as c:self.assertEqual(c.execute('SELECT count(*) AS n FROM starboard_outbox').fetchone()['n'],0)

    def test_expired_content_is_hidden_then_cascades_with_jobs_and_history(self):
        row=self.repo.observe(1,self.board['id'],1,self.source,2)
        self.now=row['expires_at']
        self.assertEqual(self.repo.entries(1,self.board['id']),[])
        self.assertFalse(any(e['entry_id']==row['id'] for e in self.repo.history(1,self.board['id'])))
        self.assertEqual(self.repo.purge_expired(),1)
        with transaction(self.url) as c:self.assertEqual(c.execute('SELECT count(*) AS n FROM starboard_outbox').fetchone()['n'],0)

    def test_durable_source_jobs_coalesce_pending_but_keep_changes_during_fetch(self):
        self.repo.enqueue_refresh(1,10,100);self.repo.enqueue_refresh(1,10,100)
        claim=self.repo.refresh_jobs.claim('generated')
        self.assertIsNotNone(claim)
        self.repo.enqueue_refresh(1,10,100);self.repo.enqueue_refresh(1,10,100)
        with transaction(self.url) as c:self.assertEqual(c.execute('SELECT count(*) AS n FROM starboard_refresh_jobs').fetchone()['n'],2)
        self.assertTrue(self.repo.refresh_jobs.finish(claim,Outcome('Generated transient error',retry=True)))
        self.assertEqual(self.repo.entries(1,self.board['id']),[])

    def test_source_retry_is_revisioned_audited_and_does_not_cross_guilds(self):
        self.repo.enqueue_refresh(1,10,100);claim=self.repo.refresh_jobs.claim('generated')
        self.repo.refresh_jobs.finish(claim,Outcome('Generated source failure'))
        self.repo.settings.set_module(2,'starboard',enabled=True,settings={})
        with self.assertRaises(LookupError):self.repo.retry_source(2,self.board['id'],claim.id,30,1)
        with self.assertRaises(RuntimeError):self.repo.retry_source(1,self.board['id'],claim.id,30,2)
        self.repo.retry_source(1,self.board['id'],claim.id,30,1)
        self.assertEqual(self.repo.delivery_history(1,self.board['id'])['source_fetches'][0]['retry_actor_id'],30)
        self.assertEqual(self.repo.history(1,self.board['id'])[0]['event_type'],'source_retry')

    def test_deleted_parent_removes_thread_snapshot_content_and_queues_withdrawal(self):
        self.repo.observe(1,self.board['id'],1,{**self.source,'channel_id':11,'parent_channel_id':10,'image_url':'https://cdn.discordapp.com/generated.png'},2)
        self.assertEqual(self.repo.delete_channel(2,10),0)
        self.assertEqual(self.repo.delete_channel(1,10),1)
        source=self.repo.entries(1,self.board['id'])[0]['snapshot']
        self.assertTrue(source['deleted']);self.assertEqual(source['content'],'');self.assertEqual(source['image_url'],'')
        self.assertEqual(self.repo.delete_channel(1,10),0)
