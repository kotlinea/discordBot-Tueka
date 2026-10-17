"""Real PostgreSQL appeals ownership, concurrency, audit and retention boundaries."""
import tempfile
import time
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, AsyncMock
from db_support import prepare_database
from database import transaction
from guild_settings import GuildSettingsRepository
from moderation import ModerationRepository
from applications.repository import ApplicationRepository
from appeals.repository import AppealRepository
from appeals.service import AppealService
from appeals.delivery import AppealDeliveryService
from discord_io import DiscordFailure


class AppealTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.url=prepare_database(Path(self.tmp.name)/'appeals',self.addCleanup)
        self.repo=AppealRepository(self.url)
        self.settings=GuildSettingsRepository(self.url)
        self.settings.set_module(1,'appeals',enabled=True,settings={'retention_days':1})
        self.moderation=ModerationRepository(self.url)
        self.case=self.moderation.add_case(1,10,'warn','generated',moderator_id=90)
        self.service=AppealService(self.repo,self.moderation,ApplicationRepository(self.url),None)

    def open(self, interaction=100, author=10):
        return self.service.open(1,author,interaction,'Generated appeal',case_id=self.case)

    def test_case_owner_guild_and_independent_review(self):
        for guild,author,case in ((2,10,self.case),(1,11,self.case),(1,10,999)):
            with self.assertRaises(PermissionError):self.service.open(guild,author,100,'test',case_id=case)
        item=self.open()
        self.assertEqual(item['kind'],'appeal')
        for actor in (10,90):
            with self.assertRaises(PermissionError):self.repo.transition(1,item['id'],actor,'accepted','generated review',revision=1)
        updated=self.repo.transition(1,item['id'],91,'accepted','Independent review',revision=1)
        self.assertEqual(updated['status'],'accepted')
        self.assertEqual(self.moderation.case(1,self.case)['action'],'warn')
        self.assertEqual(self.repo.conversation(1,item['id'])['events'][0]['event_type'],'accepted')

    def test_replay_and_parallel_open(self):
        with ThreadPoolExecutor(2) as pool:
            values=list(pool.map(lambda _: self.open(),range(2)))
        self.assertEqual(values[0]['id'],values[1]['id'])
        with self.assertRaises(RuntimeError):self.open(101)
        self.assertEqual(len(self.repo.conversation(1,values[0]['id'])['messages']),1)

    def test_modmail_owner_reply_and_staff_outbox_atomic(self):
        item=self.service.open(1,10,100,'Generated mail')
        with self.assertRaises(LookupError):self.repo.conversation(1,item['id'],author=11)
        with self.assertRaises(PermissionError):self.repo.reply(1,item['id'],11,'leak',revision=1)
        updated=self.repo.reply(1,item['id'],10,'Follow up',revision=1,interaction=101)
        self.assertEqual(self.repo.reply(1,item['id'],10,'Follow up',revision=1,interaction=101)['revision'],2)
        self.repo.reply(1,item['id'],91,'Generated staff reply',revision=updated['revision'],staff=True)
        self.assertEqual(len(self.repo.conversation(1,item['id'])['delivery']),1)
        with self.assertRaises(RuntimeError):self.repo.reply(1,item['id'],91,'stale',revision=1,staff=True)

    def test_disable_revision_and_expiry_cascade(self):
        item=self.open()
        self.settings.set_module(1,'appeals',enabled=False)
        with self.assertRaises(PermissionError):self.repo.transition(1,item['id'],91,'rejected','no',revision=1)
        self.assertEqual(self.repo.item(1,item['id'])['status'],'open')
        self.repo.purge_expired(now=int(time.time())+86401)
        self.assertEqual(self.repo.items(1),[])
        with transaction(self.url) as c:
            for table in ('appeal_messages','appeal_events','appeal_outbox'):
                self.assertEqual(c.execute(f'SELECT COUNT(*) AS n FROM {table}').fetchone()['n'],0)

    def test_withdraw_terminal_and_ticket_foreign_owner(self):
        item=self.open()
        with self.assertRaises(PermissionError):self.service.link_ticket(1,item['id'],91,999,1)
        self.repo.transition(1,item['id'],10,'withdrawn','',revision=1,withdraw=True)
        with self.assertRaises(RuntimeError):self.repo.transition(1,item['id'],91,'accepted','late',revision=2)

    def test_audit_failure_rolls_back_reply_and_notification(self):
        item=self.open()
        with patch.object(self.repo,'_event',side_effect=RuntimeError('audit_failure')):
            with self.assertRaises(RuntimeError):self.repo.reply(1,item['id'],91,'reply',revision=1,staff=True)
        self.assertEqual(self.repo.item(1,item['id'])['revision'],1)
        detail=self.repo.conversation(1,item['id'])
        self.assertEqual(len(detail['messages']),1);self.assertEqual(detail['delivery'],[])

    def test_parallel_reviews_have_one_atomic_winner(self):
        item=self.open()
        def attempt(status):
            try:return self.repo.transition(1,item['id'],91,status,'review',revision=1)['status']
            except RuntimeError:return 'conflict'
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(attempt,('accepted','rejected')))
        self.assertEqual(results.count('conflict'),1)
        detail=self.repo.conversation(1,item['id'])
        self.assertEqual(len(detail['events']),2);self.assertEqual(len(detail['delivery']),1)

    def test_each_delivery_binds_to_its_original_review_event(self):
        item=self.open()
        self.repo.transition(1,item['id'],91,'reviewing','first decision',revision=1)
        self.repo.transition(1,item['id'],92,'accepted','second decision',revision=2)
        first=self.repo.jobs.claim('first');second=self.repo.jobs.claim('second')
        self.assertEqual(self.repo.delivery(first.payload)['body'],'reviewing\nfirst decision')
        self.assertEqual(self.repo.delivery(second.payload)['body'],'accepted\nsecond decision')

    def test_public_application_and_ticket_contracts_validate_same_owner(self):
        from types import SimpleNamespace
        from test_applications import definition
        applications=ApplicationRepository(self.url)
        self.settings.set_module(1,'applications',enabled=True)
        form=applications.save_form(1,91,definition())
        application=applications.submit(1,form['id'],10,501,{'why':'Generated linked answer'},revision=1,roles=[],created_at=1,joined_at=1)
        with self.assertRaises(PermissionError):self.service.open(1,11,100,'Other person',application_id=application['id'])
        item=self.service.open(1,10,100,'Own application',application_id=application['id'])
        tickets=SimpleNamespace(ticket=lambda _:dict(id=7,guild_id=1,opener_id=10))
        service=AppealService(self.repo,self.moderation,applications,tickets)
        linked=service.link_ticket(1,item['id'],91,7,1)
        self.assertEqual(linked['ticket_id'],7)
        tickets.ticket=lambda _:dict(id=7,guild_id=2,opener_id=10)
        with self.assertRaises(PermissionError):service.link_ticket(1,item['id'],91,7,2)

    def test_expired_conversations_cannot_be_read_before_physical_cleanup(self):
        item=self.open()
        with transaction(self.url) as c:c.execute('UPDATE appeal_threads SET expires_at=0 WHERE id=%s',(item['id'],))
        self.assertEqual(self.repo.items(1),[])
        for read in (self.repo.item,self.repo.conversation):
            with self.assertRaises(LookupError):read(1,item['id'])

    def test_uncertain_dm_is_reconciled_after_retry_without_new_message(self):
        import asyncio
        from types import SimpleNamespace
        from jobs import run_batch
        item=self.open();self.repo.reply(1,item['id'],91,'generated reply',revision=1,staff=True)
        calls=[]
        async def notify(item,key,*,recover):
            calls.append(recover)
            if not recover:raise DiscordFailure('uncertain',partial=True)
            return 123
        service=AppealDeliveryService(self.repo,SimpleNamespace(notify=notify))
        asyncio.run(run_batch(self.repo.jobs,'first',service.deliver,limit=1))
        with transaction(self.url) as c:c.execute('UPDATE appeal_outbox SET available_at=0')
        asyncio.run(run_batch(self.repo.jobs,'second',service.deliver,limit=1))
        self.assertEqual(calls,[False,True])
        self.assertEqual(self.repo.conversation(1,item['id'])['delivery'][0]['discord_message_id'],123)

    def test_failed_retry_keeps_uncertain_flag_and_records_actor(self):
        item=self.open();self.repo.reply(1,item['id'],91,'reply',revision=1,staff=True)
        with transaction(self.url) as c:
            job=c.execute("UPDATE appeal_outbox SET status='failed',attempts=8,delivery_started=1 RETURNING id").fetchone()['id']
        self.repo.retry_delivery(1,item['id'],job,91,revision=2)
        detail=self.repo.conversation(1,item['id'])
        self.assertEqual(detail['delivery'][0]['delivery_started'],1)
        self.assertEqual(detail['events'][0]['event_type'],'delivery_retry')


class AppealDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_uncertain_receipt_reconciles_and_logs_no_body(self):
        from types import SimpleNamespace
        repo=SimpleNamespace(delivery=lambda job:{'id':1},delivery_state=lambda *a,**k:True)
        port=SimpleNamespace(notify=AsyncMock(side_effect=DiscordFailure('private transport detail',partial=True)))
        service=AppealDeliveryService(repo,port)
        result=await service.deliver({'id':1,'discord_message_id':None,'delivery_started':1})
        self.assertTrue(result.retry);self.assertNotIn('private',result.error)
        self.assertTrue(port.notify.call_args.kwargs['recover'])
