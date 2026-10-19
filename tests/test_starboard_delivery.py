import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from db_support import prepare_database
from database import transaction
from discord_io import DiscordFailure
from starboard.repository import StarboardRepository
from starboard.delivery import HighlightDelivery


class Adapter:
    def __init__(self,source):self.value=source;self.score=2;self.messages={};self.sent=[];self.edited=[];self.deleted=[];self.uncertain=False;self.visible=True
    async def source(self,*_):return self.value,self.score
    async def reconcile(self,guild,channel,marker):
        if not self.visible:return None
        return next((key for key,value in self.messages.items() if value==(channel,marker)),None)
    async def send(self,guild,channel,source,score,emoji,marker):
        message=1000+len(self.sent);self.sent.append(message);self.messages[message]=(channel,marker)
        if self.uncertain:self.uncertain=False;raise DiscordFailure('Generated unknown response',partial=True,retry=True)
        return message
    async def edit(self,guild,channel,message,*_):
        if message not in self.messages:raise DiscordFailure('Generated missing message',missing=True)
        self.edited.append(message)
    async def delete(self,guild,channel,message,marker):
        assert self.messages[message]==(channel,marker)
        self.messages.pop(message);self.deleted.append(message)


class HighlightDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.url=prepare_database(Path(self.tmp.name)/'highlights',self.addCleanup);self.now=1000
        self.repo=StarboardRepository(self.url,clock=lambda:self.now)
        self.repo.settings.set_module(1,'starboard',enabled=True,settings={})
        self.config={'name':'Generated','enabled':True,'target_channel_id':20,'source_channel_ids':[10],'threshold':2}
        self.board=self.repo.save_board(1,30,self.config)
        self.source={'guild_id':1,'channel_id':10,'message_id':100,'author_id':40,'author_bot':False,'content':'Generated proof'}
        self.entry=self.repo.observe(1,self.board['id'],1,self.source,2)
        self.adapter=Adapter(self.source);self.delivery=HighlightDelivery(self.repo,self.adapter)

    async def process(self):
        claim=self.repo.jobs.claim('generated-worker')
        self.assertIsNotNone(claim)
        outcome=await self.delivery.handle(claim.payload)
        self.assertTrue(self.repo.jobs.finish(claim,outcome));return outcome

    async def test_known_receipt_is_edited_then_threshold_drop_removes_only_that_message(self):
        self.assertIsNone((await self.process()).error)
        self.adapter.value={**self.source,'content':'Edited proof'}
        self.repo.observe(1,self.board['id'],1,self.adapter.value,2)
        await self.process();self.assertEqual(self.adapter.sent,[1000]);self.assertEqual(self.adapter.edited,[1000])
        self.adapter.score=1;self.repo.observe(1,self.board['id'],1,self.adapter.value,1)
        await self.process();self.assertEqual(self.adapter.deleted,[1000]);self.assertEqual(self.adapter.messages,{})

    async def test_unknown_send_is_reconciled_after_restart_without_second_send(self):
        self.adapter.uncertain=True
        self.assertTrue((await self.process()).retry)
        self.now+=100
        self.delivery=HighlightDelivery(self.repo,self.adapter)
        self.assertIsNone((await self.process()).error)
        self.assertEqual(self.adapter.sent,[1000]);self.assertEqual(self.adapter.edited,[1000])

    async def test_unknown_missing_receipt_fails_without_blind_resend(self):
        self.adapter.uncertain=True;await self.process();self.now+=100;self.adapter.visible=False
        outcome=await self.process()
        self.assertIsNotNone(outcome.error);self.assertFalse(outcome.retry);self.assertEqual(self.adapter.sent,[1000])
        with transaction(self.url) as c:self.assertEqual(c.execute('SELECT status FROM starboard_outbox').fetchone()['status'],'failed')

    async def test_target_change_retains_old_receipt_for_verified_cleanup(self):
        await self.process()
        self.repo.save_board(1,30,{**self.config,'target_channel_id':21},board=self.board['id'],revision=1)
        await self.process()
        self.assertEqual(self.adapter.deleted,[1000]);self.assertEqual(self.adapter.sent,[1000,1001])
        with transaction(self.url) as c:
            values=c.execute('SELECT target_channel_id,message_id,removed FROM starboard_publications ORDER BY id').fetchall()
        self.assertEqual([(r['target_channel_id'],r['message_id'],r['removed']) for r in values],[(20,1000,1),(21,1001,0)])

    async def test_off_blocks_delivery_and_delete_tombstone_survives_until_reenabled(self):
        await self.process()
        self.repo.settings.set_module(1,'starboard',enabled=False)
        try:
            self.assertEqual(self.repo.delete_source(1,10,[100]),1)
            self.assertIsNone(self.repo.jobs.claim('paused'))
            self.assertEqual(self.adapter.deleted,[])
        finally:self.repo.settings.set_module(1,'starboard',enabled=True)
        self.now+=100;await self.process();self.assertEqual(self.adapter.deleted,[1000])

    async def test_a_new_source_revision_during_send_queues_followup(self):
        original=self.adapter.send
        async def changing(*args):
            result=await original(*args)
            self.adapter.value={**self.source,'content':'Changed during send'}
            self.repo.observe(1,self.board['id'],1,self.adapter.value,2)
            return result
        self.adapter.send=changing
        await self.process();await self.process()
        self.assertEqual(self.adapter.sent,[1000]);self.assertEqual(self.adapter.edited,[1000])

    async def test_board_off_after_settled_before_finish_keeps_one_durable_followup(self):
        claim = self.repo.jobs.claim('first-worker')
        outcome = await self.delivery.handle(claim.payload)
        self.assertIsNone(outcome.error)  # Revision check ran; queue finish has not.
        board = self.repo.save_board(1, 30, {**self.config, 'enabled': False},
            board=self.board['id'], revision=1)
        self.repo.save_board(1, 30, {**self.config, 'enabled': False, 'name': 'Latest'},
            board=board['id'], revision=board['revision'])
        with transaction(self.url) as c:
            self.assertEqual([r['status'] for r in c.execute('SELECT status FROM starboard_outbox ORDER BY id')],
                ['processing', 'pending'])
        self.assertTrue(self.repo.jobs.finish(claim, outcome))
        self.repo = StarboardRepository(self.url, clock=lambda: self.now)
        self.delivery = HighlightDelivery(self.repo, self.adapter)
        self.assertIsNone((await self.process()).error)
        self.assertEqual(self.adapter.sent, [1000])
        self.assertEqual(self.adapter.deleted, [1000])
        self.assertEqual(self.adapter.messages, {})
        self.assertIsNone(self.repo.jobs.claim('empty'))

    async def test_unexpected_errors_do_not_store_private_exception_text(self):
        async def unexpected(*_):raise RuntimeError('private generated credential text')
        self.adapter.source=unexpected
        outcome=await self.process()
        self.assertTrue(outcome.retry);self.assertNotIn('private',outcome.error)
        self.assertIn('RuntimeError',outcome.error)
