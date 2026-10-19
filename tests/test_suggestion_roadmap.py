"""Taxonomy and duplicate-merge rules independent of HTTP and Discord."""
import unittest
import tempfile
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from db_support import prepare_database
from database import transaction
from guild_settings import GuildSettingsRepository
from suggestions import SuggestionRepository
from suggestions.roadmap import labels,merge,taxonomy


class RoadmapRulesTests(unittest.TestCase):
    def test_taxonomy_keeps_unicode_names_and_rejects_duplicates_and_controls(self):
        self.assertEqual(taxonomy(['  改善  ','New'],'categories',20),['改善','New'])
        for values in (['New','new'],[''],['line\nbreak'],['x'*41],[1],['a']*21):
            with self.subTest(values=values),self.assertRaises(ValueError):
                taxonomy(values,'categories',20)

    def test_metadata_uses_canonical_registered_labels_and_bounded_tags(self):
        config={'categories':['改善','Community'],'tags':['UI','Help']}
        self.assertEqual(labels('community',['ui'],config),{'category':'Community','tags':['UI']})
        self.assertEqual(labels('',[],config),{'category':'','tags':[]})
        for category,tags in (('Unknown',[]),('', ['Unknown']),('', ['UI','ui'])):
            with self.assertRaises(ValueError):labels(category,tags,config)

    def rows(self):
        return ({'id':1,'guild_id':10,'status':'pending','revision':2,'merged_into':None,'expires_at':None},
                {'id':2,'guild_id':10,'status':'implemented','revision':3,'merged_into':None,'expires_at':1000})

    def test_merge_allows_a_duplicate_of_an_implemented_canonical_target(self):
        source,target=self.rows()
        self.assertEqual(merge(source,target,' Duplicate proof ',2,3,100),'Duplicate proof')
        self.assertEqual(source['status'],'pending');self.assertEqual(target['status'],'implemented')

    def test_merge_rejects_self_cross_guild_expired_and_stale_revisions(self):
        source,target=self.rows()
        with self.assertRaises(ValueError):merge(source,source,'same',2,2,100)
        with self.assertRaises(PermissionError):merge(source,{**target,'guild_id':11},'cross',2,3,100)
        with self.assertRaises(LookupError):merge(source,target,'expired',2,3,1000)
        for left,right in ((1,3),(2,4),(True,3)):
            with self.assertRaises(RuntimeError):merge(source,target,'stale',left,right,100)

    def test_merge_requires_canonical_targets_and_explicit_reason(self):
        source,target=self.rows()
        for row in ({**target,'merged_into':3},{**target,'status':'delivery_failed'}):
            with self.assertRaises(RuntimeError):merge(source,row,'duplicate',2,3,100)
        for reason in ('','  ','x'*1001,None):
            with self.assertRaises(ValueError):merge(source,target,reason,2,3,100)


class RoadmapRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.url=prepare_database(Path(self.tmp.name)/'roadmap',self.addCleanup)
        self.repo=SuggestionRepository(self.url)
        self.settings=GuildSettingsRepository(self.url)
        self.settings.set_module(1,'suggestions',enabled=True,settings={'categories':['改善'],'tags':['UI','Docs'],'retention_days':1})

    def create(self,guild=1):return self.repo.create(guild,10,20,{'idea':'Generated roadmap test'})

    def merge(self,source,target):
        source=self.repo.get(1,source['id']);target=self.repo.get(1,target['id'])
        return self.repo.merge(1,source['id'],target['id'],40,'Generated duplicate proof',source['revision'],target['revision'])

    def test_labels_are_registered_audited_revisioned_and_filterable(self):
        item=self.create()
        updated=self.repo.set_labels(1,item['id'],40,'改善',['UI'],1)
        self.assertEqual(updated['category'],'改善');self.assertEqual(updated['tags'],['UI'])
        self.assertEqual(len(self.repo.list(1,category='改善',tag='UI')),1)
        self.assertEqual(self.repo.list(1,tag='Docs'),[])
        self.assertEqual(self.repo.events(1,item['id'])[0]['event_type'],'labels_changed')
        with self.assertRaises(RuntimeError):self.repo.set_labels(1,item['id'],40,'',[],1)
        self.settings.set_module(1,'suggestions',enabled=False)
        with self.assertRaises(PermissionError):self.repo.set_labels(1,item['id'],40,'',[],2)

    def test_merge_deduplicates_voters_keeps_original_votes_and_can_cancel_inherited_vote(self):
        source,target=self.create(),self.create()
        self.repo.vote(1,source['id'],30,1);self.repo.vote(1,target['id'],30,-1)
        self.repo.vote(1,source['id'],31,1)
        merged=self.merge(source,target)
        self.assertEqual(merged['status'],'merged');self.assertEqual(merged['merged_into'],target['id'])
        self.assertEqual((merged['upvotes'],merged['downvotes']),(1,1))
        with transaction(self.url) as c:
            self.assertEqual(c.execute('SELECT count(*) AS n FROM suggestion_votes WHERE suggestion_id=%s',(source['id'],)).fetchone()['n'],2)
        self.repo.vote(1,target['id'],31,1)
        result=self.repo.get(1,target['id'])
        self.assertEqual((result['upvotes'],result['downvotes']),(0,1))
        self.repo.vote(1,target['id'],31,-1)
        self.assertEqual(self.repo.get(1,target['id'])['downvotes'],2)
        with self.assertRaises(RuntimeError):self.repo.vote(1,source['id'],32,1)
        self.assertTrue(any(e['event_type']=='merged' for e in self.repo.events(1,source['id'])))

    def test_merge_existing_group_retargets_sources_without_cycles_or_history_loss(self):
        first,middle,last=self.create(),self.create(),self.create()
        self.merge(first,middle);self.merge(middle,last)
        self.assertEqual(self.repo.get(1,first['id'])['merged_into'],last['id'])
        events=self.repo.events(1,first['id'])
        self.assertTrue(any(e['event_type']=='merged' and e['detail']['target_id']==middle['id'] for e in events))
        self.assertTrue(any(e['event_type']=='merge_retargeted' for e in events))
        with self.assertRaises(RuntimeError):self.merge(last,first)

    def test_parallel_merge_has_one_winner_and_cross_guild_is_missing(self):
        source,left,right=self.create(),self.create(),self.create()
        def attempt(target):
            try:return self.repo.merge(1,source['id'],target['id'],40,'Duplicate',1,1)['merged_into']
            except RuntimeError:return None
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(attempt,(left,right)))
        self.assertEqual(sum(result is not None for result in results),1)
        foreign=self.create(2)
        with self.assertRaises(LookupError):self.repo.merge(1,left['id'],foreign['id'],40,'Cross Guild',1,1)

    def test_audit_failure_rolls_back_labels_and_merge_with_outbox(self):
        source,target=self.create(),self.create()
        with transaction(self.url) as c:before=c.execute('SELECT count(*) AS n FROM suggestion_outbox').fetchone()['n']
        with patch.object(self.repo,'_roadmap_event',side_effect=RuntimeError('audit_failure')):
            with self.assertRaises(RuntimeError):self.repo.set_labels(1,source['id'],40,'改善',['UI'],1)
            with self.assertRaises(RuntimeError):self.merge(source,target)
        self.assertEqual(self.repo.get(1,source['id'])['revision'],1)
        self.assertIsNone(self.repo.get(1,source['id'])['merged_into'])
        with transaction(self.url) as c:self.assertEqual(c.execute('SELECT count(*) AS n FROM suggestion_outbox').fetchone()['n'],before)

    def test_new_expiry_hides_reads_and_cascades_but_does_not_expire_legacy_records(self):
        item=self.create();legacy=self.create()
        self.assertEqual(item['expires_at']-item['created_at'],86400)
        with transaction(self.url) as c:
            c.execute('UPDATE suggestions SET expires_at=NULL WHERE id=%s',(legacy['id'],))
            c.execute('UPDATE suggestions SET expires_at=1 WHERE id=%s',(item['id'],))
        self.assertIsNone(self.repo.get(1,item['id']))
        with self.assertRaises(LookupError):self.repo.events(1,item['id'])
        self.settings.set_module(1,'suggestions',enabled=False)
        self.assertEqual(self.repo.purge_expired(),1)
        self.assertEqual([row['id'] for row in self.repo.list(1)],[legacy['id']])
        with transaction(self.url) as c:
            for table in ('suggestion_events','suggestion_outbox','suggestion_votes'):
                self.assertEqual(c.execute(f'SELECT count(*) AS n FROM {table} WHERE suggestion_id=%s',(item['id'],)).fetchone()['n'],0)
