"""Run in canonical test-python with isolated PostgreSQL; no real Discord."""
import asyncio
import unittest
import uuid
from db_support import prepare_database
from jobs import LostLease, Outcome
from discord_io import DiscordFailure
from database import transaction
from starboard.repository import StarboardRepository
from starboard.delivery import HighlightDelivery
from test_starboard_delivery import Adapter


class LateHighlightEditProbe(unittest.IsolatedAsyncioTestCase):
    async def test_late_expired_edit_must_leave_durable_repair(self):
        await self.late_edit()

    async def test_late_edit_response_loss_must_leave_durable_repair(self):
        await self.late_edit(response_loss=True)

    async def test_cancellation_waits_for_accepted_edit_before_repair(self):
        await self.late_edit(cancel=True)

    async def late_edit(self, *, response_loss=False, cancel=False):
        self.now = 1000
        url = prepare_database('public-boards-independent-' + uuid.uuid4().hex, self.addCleanup)
        repo = StarboardRepository(url, clock=lambda: self.now)
        repo.settings.set_module(1, 'starboard', enabled=True)
        config = {'name':'Proof', 'enabled':True, 'target_channel_id':20, 'source_channel_ids':[10], 'threshold':2}
        board = repo.save_board(1, 30, config)
        source = {'guild_id':1, 'channel_id':10, 'message_id':100, 'author_id':40, 'author_bot':False, 'content':'Initial'}
        repo.observe(1, board['id'], 1, source, 2)
        adapter = Adapter(source)
        delivery = HighlightDelivery(repo, adapter)
        initial = repo.jobs.claim('initial')
        self.assertIsNone((await delivery.handle(initial.payload)).error)
        self.assertTrue(repo.jobs.finish(initial, Outcome()))
        adapter.value = {**source, 'content':'Old'}
        repo.observe(1, board['id'], 1, adapter.value, 2)
        old = repo.jobs.claim('old', lease_seconds=3)
        started, release = asyncio.Event(), asyncio.Event()
        first = True
        external = {'content':'Initial'}
        async def edit(guild, channel, message, snapshot, *args):
            nonlocal first
            gated = first
            first = False
            if gated:
                started.set()
                await release.wait()
            external['content'] = snapshot['content']
            if gated and response_loss:
                raise DiscordFailure('Generated delayed response loss', retry=True, partial=True)
        adapter.edit = edit
        task = asyncio.create_task(delivery.handle(old.payload))
        try:
            await asyncio.wait_for(started.wait(), 5)
            adapter.value = {**source, 'content':'Latest'}
            repo.observe(1, board['id'], 1, adapter.value, 2)
            self.now += 4
            # Expired job takeover, then the durable successor created by observe.
            for owner in ('replacement', 'successor'):
                claim = repo.jobs.claim(owner)
                self.assertIsNotNone(claim)
                self.assertIsNone((await delivery.handle(claim.payload)).error)
                self.assertTrue(repo.jobs.finish(claim, Outcome()))
            self.assertEqual(external['content'], 'Latest')
            self.assertIsNone(repo.jobs.claim('empty-before-late-response'))
            if cancel:task.cancel()
            release.set()
            if cancel:
                with self.assertRaises(asyncio.CancelledError):await task
            elif response_loss:self.assertTrue((await task).retry)
            else:
                with self.assertRaises(LostLease):await task
            self.assertFalse(repo.jobs.finish(old, Outcome()))
            self.assertEqual(external['content'], 'Old')
            self.assertEqual(repo.entries(1, board['id'])[0]['snapshot']['content'], 'Latest')
            repair = repo.jobs.claim('repair-after-late-completion')

            self.assertIsNotNone(repair, 'Late old edit must reserve repair work')
            self.assertIsNone((await delivery.handle(repair.payload)).error)
            self.assertTrue(repo.jobs.finish(repair, Outcome()))
            self.assertEqual(external['content'], 'Latest')
            self.assertIsNone(repo.jobs.claim('empty-after-repair'))
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)

    async def test_repair_is_scoped_coalesced_paused_and_retention_bound(self):
        self.now=1000
        url=prepare_database('highlight-repair-scope-'+uuid.uuid4().hex,self.addCleanup)
        repo=StarboardRepository(url,clock=lambda:self.now)
        repo.settings.set_module(1,'starboard',enabled=True)
        config={'name':'Proof','enabled':True,'target_channel_id':20,'source_channel_ids':[10],'threshold':2,'retention_days':1}
        board=repo.save_board(1,30,config)
        source={'guild_id':1,'channel_id':10,'message_id':100,'author_id':40,'author_bot':False,'content':'Private body'}
        entry=repo.observe(1,board['id'],1,source,2)
        old=repo.jobs.claim('old',lease_seconds=3)
        # A still-owned failure uses its ordinary retry, not a second job.
        repo.delivery_repair(1,entry['id'],old.payload)
        self.assertIsNone(repo.jobs.claim('no-extra-while-owned'))
        self.now+=4
        replacement=repo.jobs.claim('replacement')
        self.assertTrue(repo.jobs.finish(replacement,Outcome()))
        repo.delivery_repair(2,entry['id'],old.payload)
        self.assertIsNone(repo.jobs.claim('wrong-guild'))
        repo.settings.set_module(1,'starboard',enabled=False)
        repo.delete_source(1,10,[100])
        for _ in range(3):repo.delivery_repair(1,entry['id'],old.payload)
        self.assertIsNone(repo.jobs.claim('paused'))
        self.assertTrue(repo.entries(1,board['id'])[0]['snapshot']['deleted'])
        self.assertEqual(repo.entries(1,board['id'])[0]['snapshot']['content'],'')
        repo.settings.set_module(1,'starboard',enabled=True)
        repair=repo.jobs.claim('one-repair')
        self.assertIsNotNone(repair)
        self.assertTrue(repo.jobs.finish(repair,Outcome()))
        self.assertIsNone(repo.jobs.claim('no-duplicate'))
        self.now=entry['expires_at']
        repo.delivery_repair(1,entry['id'],old.payload)
        self.assertIsNone(repo.jobs.claim('expired-not-repaired'))
        self.assertEqual(repo.purge_expired(),1)
        repo.delivery_repair(1,entry['id'],old.payload)
        self.assertIsNone(repo.jobs.claim('purged-not-resurrected'))
        with transaction(url) as c:
            self.assertEqual(c.execute('SELECT count(*) AS n FROM starboard_expired_sources').fetchone()['n'],1)

