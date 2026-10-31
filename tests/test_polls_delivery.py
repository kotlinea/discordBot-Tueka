"""AP-DELIVERY/RETENTION: publication receipts, leases, move and deadline recovery."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from database import transaction
from database.testing import temporary_database
from jobs import Outcome, LostLease
from discord_io import DiscordFailure
from engagement.polls.repository import PollRepository
from engagement.polls.delivery import PollDelivery
from engagement.polls.models import PollError


class PollDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        ctx=temporary_database();self.url=ctx.__enter__();self.addCleanup(ctx.__exit__,None,None,None)
        self.now=1000000
        self.repo=PollRepository(self.url,clock=lambda:self.now)
        self.repo.settings.set_module(1,'advanced_polls',enabled=True)
        self.item=self.repo.create(1,10,20,dict(question='Q',options=['A','B']),'new',duration_seconds=100)
        self.port=NS(deliver=AsyncMock(return_value=500))
        self.service=PollDelivery(self.repo,self.port)

    def claim(self):
        return self.repo.jobs.claim('test',lease_seconds=3)

    def launch(self):
        self.repo.launch(1,self.item['id'],20,1)

    async def test_publish_receipt_and_relative_deadline(self):
        self.launch();job=self.claim()
        outcome=await self.service.deliver(job.payload)
        self.assertTrue(self.repo.jobs.finish(job,outcome))
        result=self.repo.get(1,self.item['id'])
        self.assertEqual((result['message_id'],result['status'],result['closes_at']),(500,'open',self.now+100))
        self.assertIn(500,self.repo.pending_displays())

    async def test_uncertain_send_is_only_reconciled(self):
        self.launch();job=self.claim()
        self.port.deliver.side_effect=DiscordFailure('uncertain',retry=True,partial=True)
        outcome=await self.service.deliver(job.payload)
        self.assertTrue(outcome.retry);self.repo.jobs.finish(job,outcome)
        self.now+=100
        resumed=PollRepository(self.url,clock=lambda:self.now)
        self.port.deliver.side_effect=None
        job=resumed.jobs.claim('new-owner',lease_seconds=3)
        await PollDelivery(resumed,self.port).deliver(job.payload)
        self.assertTrue(self.port.deliver.await_args.kwargs['recover'])

    async def test_lost_receipt_lease_does_not_publish(self):
        self.launch();job=self.claim()
        async def slow(*args,**kwargs):self.now+=3;return 500
        self.port.deliver.side_effect=slow
        with self.assertRaises(LostLease):await self.service.deliver(job.payload)
        self.assertIsNone(self.repo.get(1,self.item['id'])['message_id'])
        next_job=self.claim()
        state,_=self.repo.start_delivery(next_job.payload)
        self.assertEqual(state,'recover')

    async def test_module_off_does_not_consume_attempt(self):
        self.launch();self.repo.settings.set_module(1,'advanced_polls',enabled=False)
        self.assertIsNone(self.claim())
        self.repo.settings.set_module(1,'advanced_polls',enabled=True)
        self.assertEqual(self.claim().attempt,1)

    async def test_move_preserves_ballots_and_rejects_old_post(self):
        self.launch();job=self.claim();self.repo.jobs.finish(job,await self.service.deliver(job.payload))
        item=self.repo.get(1,self.item['id']);self.repo.vote(1,item['id'],30,[0],message_id=500,revision=item['revision'])
        self.repo.launch(1,item['id'],20,item['revision'],channel=11)
        self.port.deliver.return_value=501
        job=self.claim();self.repo.jobs.finish(job,await self.service.deliver(job.payload))
        item=self.repo.get(1,item['id'])
        self.assertEqual((item['channel_id'],item['counts']),(11,[1,0]))
        with self.assertRaises(PollError):self.repo.vote(1,item['id'],30,[1],message_id=500,revision=item['revision'])
        cleanup=self.claim()
        self.assertEqual(cleanup.payload['action'],'stop_old')
        self.assertEqual(cleanup.payload['old_message_id'],500)

    async def test_expired_schedule_does_not_send(self):
        item=self.repo.create(1,10,20,dict(question='S',options=['A','B']),'scheduled',scheduled_at=self.now+5,closes_at=self.now+10)
        self.now+=20;self.repo.enqueue_due();job=self.claim()
        self.assertIsNotNone(job)
        self.assertEqual((await self.service.deliver(job.payload)).error,None)
        self.port.deliver.assert_not_awaited()
        self.assertEqual(self.repo.get(1,item['id'])['status'],'closed')

    async def test_deadline_passed_during_send_has_terminal_retention_date(self):
        item=self.repo.create(1,10,20,dict(question='Deadline',options=['A','B']),'late-send',closes_at=self.now+5)
        self.repo.launch(1,item['id'],20,item['revision'])
        job=self.claim()
        async def send(*args,**kwargs):self.now+=6;return 500
        # Keep the lease live; only the absolute poll deadline expires.
        self.repo.jobs.renew(job,lease_seconds=60)
        self.port.deliver.side_effect=send
        await self.service.deliver(job.payload)
        result=self.repo.get(1,item['id'])
        self.assertEqual(result['status'],'closed')
        self.assertEqual(result['closed_at'],self.now)

    async def test_retention_keeps_uncertain_send(self):
        self.launch();job=self.claim();self.repo.start_delivery(job.payload)
        self.now+=10000000
        with transaction(self.url) as c:c.execute("UPDATE polls SET status='closed',closed_at=1 WHERE id=%s",(self.item['id'],))
        self.assertEqual(self.repo.purge_expired(),0)

    async def test_creation_replay_after_edit(self):
        self.repo.edit(1,self.item['id'],20,{**self.item['config'],'question':'Changed'},1)
        self.now+=100000
        replay=self.repo.create(1,10,20,dict(question='Q',options=['A','B']),'new',duration_seconds=100)
        self.assertEqual(replay['config']['question'],'Changed')
        with self.assertRaises(PollError):self.repo.create(1,10,21,dict(question='Q',options=['A','B']),'new',duration_seconds=100)

    async def automation_poll(self,key,*,close=True,**config):
        item=self.repo.create(1,10,20,dict(question='Q',options=['A','B'],announce_winner=True,pin_on_close=True,**config),key)
        self.port.deliver.return_value=500+item['id']
        self.repo.launch(1,item['id'],20,item['revision'])
        job=self.claim();self.repo.jobs.finish(job,await self.service.deliver(job.payload))
        with transaction(self.url) as c:c.execute('UPDATE polls SET thread_id=700 WHERE id=%s',(item['id'],))
        item=self.repo.get(1,item['id'])
        return self.repo.transition(1,item['id'],20,'close',item['revision']) if close else item

    async def drain_actions(self):
        self.port.deliver.reset_mock()
        while (job:=self.claim()) is not None:
            self.repo.jobs.finish(job,await self.service.deliver(job.payload))
        return [call.args[0]['action'] for call in self.port.deliver.await_args_list]

    async def test_closing_actions_follow_current_requirements_not_cosmetic_revision(self):
        cases=(('unchanged',{'announce','pin','archive'}),('cosmetic',{'announce','pin','archive'}),
               ('hide_results',{'pin','archive'}),('disable_announce',{'pin','archive'}),
               ('disable_pin',{'announce','archive'}),('reopen',set()),('delete',{'archive'}),
               ('reclose',{'announce','pin','archive'}))
        for change,expected in cases:
            with self.subTest(change=change):
                item=await self.automation_poll('actions-'+change)
                if change in ('reopen','reclose'):
                    item=self.repo.transition(1,item['id'],20,'reopen',item['revision'])
                    if change=='reclose':self.repo.transition(1,item['id'],20,'close',item['revision'])
                elif change=='delete':self.repo.transition(1,item['id'],20,'delete',item['revision'])
                elif change!='unchanged':
                    values={'cosmetic':{'color':0xffffff,'image_url':'https://example.com/poll.png'},
                            'hide_results':{'mode':'custom','visibility':{'open':{},'closed':{}}},
                            'disable_announce':{'announce_winner':False},'disable_pin':{'pin_on_close':False}}[change]
                    self.repo.edit(1,item['id'],20,{**item['config'],**values},item['revision'])
                actions=await self.drain_actions()
                self.assertCountEqual(actions,expected)
                if change=='cosmetic':
                    for call in self.port.deliver.await_args_list:
                        self.assertEqual(call.args[1]['config']['color'],0xffffff)

    async def test_started_closing_action_still_reconciles_after_edit(self):
        item=await self.automation_poll('uncertain-close')
        job=self.claim()
        self.assertEqual(self.repo.start_delivery(job.payload)[0],'send')
        self.repo.edit(1,item['id'],20,{**item['config'],'color':0xffffff},item['revision'])
        await self.service.deliver(job.payload)
        self.assertTrue(self.port.deliver.await_args.kwargs['recover'])

    async def test_cosmetic_edits_preserve_actions_for_every_closing_trigger(self):
        for trigger in ('manual','deadline','participant_limit'):
            with self.subTest(trigger=trigger):
                item=await self.automation_poll('trigger-'+trigger,close=False,max_participants=1 if trigger=='participant_limit' else None)
                if trigger=='manual':self.repo.transition(1,item['id'],20,'close',item['revision'])
                elif trigger=='deadline':
                    self.repo.edit(1,item['id'],20,item['config'],item['revision'],closes_at=self.now+1)
                    self.now+=1;self.repo.close_expired()
                else:self.repo.vote(1,item['id'],30,[0],revision=item['revision'])
                closed=self.repo.get(1,item['id'])
                self.repo.edit(1,item['id'],20,{**closed['config'],'color':0xffffff},closed['revision'])
                self.assertCountEqual(await self.drain_actions(),('announce','pin','archive'))
