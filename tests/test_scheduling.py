"""Schedules use real isolated PostgreSQL; transport alone is mocked."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from db_support import prepare_database
from database import transaction
from guild_settings import GuildSettingsRepository
from jobs import Outcome, LostLease
from scheduling.repository import ScheduleRepository
from scheduling.service import normalize
from scheduling.delivery import ScheduleDeliveryService
from scheduling.discord_adapter import DiscordScheduleAdapter
from discord_io import DiscordFailure


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.url = prepare_database(Path(self.tmp.name)/'scheduling', self.addCleanup)
        self.now = 2_000_000_000
        self.repo = ScheduleRepository(self.url, clock=lambda:self.now)
        self.settings = GuildSettingsRepository(self.url)
        self.settings.set_module(1,'scheduled_messages',enabled=True,settings={'retention_days':1})

    def values(self, **extra):
        return dict(kind='message',title='Generated',body='Test',channel_id=10,run_at=2_000_000_060,**extra)

    def create(self, **extra):
        return self.repo.create(1,20,self.values(**extra),'request-1')

    def reserve(self, **extra):
        item = self.create(**extra)
        self.now += 60
        self.repo.enqueue_due()
        return item,self.repo.jobs.claim('worker')

    def test_validation_rejects_invalid_times_recurrence_and_payload(self):
        for fields in ({'run_at':self.now},{'interval_seconds':60},{'occurrences':2},
                       {'channel_id':True},{'color':-1},{'body':'x'*2001},{'title':'','body':''}):
            with self.subTest(fields=fields),self.assertRaises(ValueError):
                normalize({**self.values(),**fields},self.now)
        event = dict(kind='event',title='Event',body='Test',run_at=self.now+60,event_start=self.now+180,event_end=self.now+360,event_location='Test venue')
        self.assertEqual(normalize(event,self.now)['kind'],'event')
        for fields in ({'event_end':self.now+100},{'event_location':'javascript://bad'},{'interval_seconds':86400,'occurrences':2}):
            with self.assertRaises(ValueError):normalize({**event,**fields},self.now)

    def test_concurrent_create_is_idempotent_and_payload_mismatch_conflicts(self):
        with ThreadPoolExecutor(2) as pool:
            rows=list(pool.map(lambda _:self.create(),range(2)))
        self.assertEqual(rows[0]['id'],rows[1]['id'])
        with self.assertRaises(RuntimeError):self.repo.create(1,20,{**self.values(),'body':'other'},'request-1')
        with self.assertRaises(LookupError):self.repo.item(2,rows[0]['id'])
        self.now+=3600
        self.assertEqual(self.create()['id'],rows[0]['id'])

    def test_reservation_restart_and_parallel_tick_exactly_one_occurrence(self):
        item=self.create();self.now+=60
        with ThreadPoolExecutor(2) as pool:list(pool.map(lambda _:self.repo.enqueue_due(),range(2)))
        self.assertEqual(len(self.repo.history(1,item['id'])['delivery']),1)
        restarted=ScheduleRepository(self.url,clock=lambda:self.now)
        self.assertEqual(restarted.enqueue_due(),0)
        self.assertEqual(restarted.item(1,item['id'])['status'],'completed')

    def test_disabled_does_not_reserve_then_skips_missed_slots_without_burst(self):
        item=self.create(interval_seconds=86400,occurrences=3)
        self.settings.set_module(1,'scheduled_messages',enabled=False)
        self.now+=2*86400+60
        self.assertEqual(self.repo.enqueue_due(),0)
        self.settings.set_module(1,'scheduled_messages',enabled=True)
        self.assertEqual(self.repo.enqueue_due(),1)
        detail=self.repo.history(1,item['id'])
        self.assertEqual(len(detail['delivery']),1)
        self.assertEqual(detail['delivery'][0]['due_at'],2_000_000_060+2*86400)
        self.assertEqual(next(e['detail'] for e in detail['events'] if e['event_type']=='missed'),'2')

    def test_all_expired_slots_create_no_delivery_and_audit_missed(self):
        item=self.create();self.now+=661
        self.repo.enqueue_due()
        self.assertEqual(self.repo.history(1,item['id'])['delivery'],[])
        self.assertEqual(self.repo.item(1,item['id'])['status'],'completed')

    def test_disabled_low_id_guild_does_not_starve_enabled_guild(self):
        self.create()
        self.settings.set_module(2,'scheduled_messages',enabled=True)
        other=self.repo.create(2,20,self.values(),'other')
        self.settings.set_module(1,'scheduled_messages',enabled=False)
        self.now+=60
        self.assertEqual(self.repo.enqueue_due(limit=1),1)
        self.assertEqual(len(self.repo.history(2,other['id'])['delivery']),1)

    def test_edit_revision_and_cancel_fence_claim_before_send(self):
        item=self.create()
        with self.assertRaises(RuntimeError):self.repo.reschedule(1,item['id'],20,self.values(),2)
        item=self.repo.reschedule(1,item['id'],20,{**self.values(),'title':'Changed'},1)
        self.now+=60;self.repo.enqueue_due()
        claim=self.repo.jobs.claim('worker')
        item=self.repo.item(1,item['id'])
        self.repo.cancel(1,item['id'],20,item['revision'])
        with self.assertRaises(PermissionError):self.repo.start_delivery(claim.payload)
        self.assertFalse(self.repo.jobs.finish(claim,Outcome()))

    def test_started_unknown_cannot_be_cancelled_or_edited_and_recovers_without_resend(self):
        item,claim=self.reserve()
        self.assertEqual(self.repo.start_delivery(claim.payload),'send')
        with self.assertRaises(RuntimeError):self.repo.cancel(1,item['id'],20,2)
        self.now+=61
        recovered=self.repo.jobs.claim('replacement')
        self.assertEqual(self.repo.start_delivery(recovered.payload),'recover')
        self.assertFalse(self.repo.delivery_state(claim.payload,receipt=111))
        self.assertTrue(self.repo.delivery_state(recovered.payload,receipt=222))
        self.assertTrue(self.repo.jobs.finish(recovered,Outcome()))
        self.repo.cancel(1,item['id'],20,2)

    def test_purge_works_when_disabled_and_cascades_history(self):
        item,claim=self.reserve()
        self.repo.jobs.finish(claim,Outcome())
        self.settings.set_module(1,'scheduled_messages',enabled=False)
        self.now+=86401
        self.assertEqual(self.repo.items(1),[])
        self.assertEqual(self.repo.purge_expired(),1)
        with transaction(self.url) as c:
            for name in ('scheduled_posts','scheduled_post_events','scheduled_post_outbox'):
                self.assertEqual(c.execute(f'SELECT count(*) AS n FROM {name}').fetchone()['n'],0)

    def test_atomic_audit_failure_does_not_leave_schedule(self):
        with patch.object(self.repo,'_event',side_effect=RuntimeError('audit')):
            with self.assertRaises(RuntimeError):self.create()
        self.assertEqual(self.repo.items(1),[])

    def test_delivery_unknown_and_receipt_are_durable_across_restart(self):
        item,claim=self.reserve()
        port=SimpleNamespace(deliver=AsyncMock(side_effect=DiscordFailure('unknown',partial=True)))
        outcome=asyncio.run(ScheduleDeliveryService(self.repo,port).deliver(claim.payload))
        self.assertTrue(outcome.retry)
        self.assertTrue(self.repo.jobs.finish(claim,outcome))
        self.now+=61
        retry=self.repo.jobs.claim('replacement')
        port.deliver=AsyncMock(return_value=1234)
        self.assertIsNone(asyncio.run(ScheduleDeliveryService(self.repo,port).deliver(retry.payload)).error)
        self.assertTrue(port.deliver.call_args.kwargs['recover'])
        self.assertTrue(self.repo.jobs.finish(retry,Outcome()))
        self.assertEqual(self.repo.history(1,item['id'])['delivery'][0]['discord_receipt_id'],1234)

    def test_disabled_and_deadline_prevent_fresh_external_io(self):
        item,claim=self.reserve()
        port=SimpleNamespace(deliver=AsyncMock(return_value=1234))
        self.settings.set_module(1,'scheduled_messages',enabled=False)
        outcome=asyncio.run(ScheduleDeliveryService(self.repo,port).deliver(claim.payload))
        self.assertTrue(outcome.retry);port.deliver.assert_not_awaited()
        self.assertTrue(self.repo.jobs.finish(claim,outcome))
        self.settings.set_module(1,'scheduled_messages',enabled=True)
        self.now+=700
        retry=self.repo.jobs.claim('expired')
        outcome=asyncio.run(ScheduleDeliveryService(self.repo,port).deliver(retry.payload))
        self.assertEqual(outcome.error,'schedule_deadline_passed');self.assertFalse(outcome.retry)
        port.deliver.assert_not_awaited()
        self.assertTrue(self.repo.jobs.finish(retry,outcome))
        with self.assertRaises(RuntimeError):self.repo.retry(1,item['id'],claim.id,20,2)

    def test_edit_is_rejected_after_reservation_even_for_later_repeat(self):
        item,claim=self.reserve(interval_seconds=86400,occurrences=2)
        values={**self.values(),'run_at':self.now+60}
        with self.assertRaises(RuntimeError):self.repo.reschedule(1,item['id'],20,values,2)
        self.assertEqual(self.repo.item(1,item['id'])['remaining'],1)

    def test_expired_retry_cannot_send_fresh_and_failed_unknown_can_only_reconcile(self):
        item,claim=self.reserve()
        self.repo.start_delivery(claim.payload)
        self.repo.jobs.finish(claim,Outcome('uncertain'))
        self.now+=700
        self.repo.retry(1,item['id'],claim.id,20,2)
        retry=self.repo.jobs.claim('replacement')
        self.assertEqual(self.repo.start_delivery(retry.payload),'recover')
        self.repo.jobs.finish(retry,Outcome())
        with self.assertRaises(RuntimeError):self.repo.retry(1,item['id'],claim.id,20,2)


class ScheduleAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setup_port(self, messages=()):
        channel=MagicMock(spec=discord.TextChannel)
        channel.guild=SimpleNamespace(id=1)
        channel.permissions_for.return_value=SimpleNamespace(view_channel=True,read_message_history=True,send_messages=True,embed_links=True)
        channel.send=AsyncMock(return_value=SimpleNamespace(id=44))
        async def history(**_):
            for item in messages:yield item
        channel.history=history
        guild=SimpleNamespace(id=1,me=SimpleNamespace(guild_permissions=SimpleNamespace(manage_events=True)),
            fetch_scheduled_events=AsyncMock(return_value=[]),create_scheduled_event=AsyncMock(return_value=SimpleNamespace(id=55)))
        bot=SimpleNamespace(user=SimpleNamespace(id=99),get_guild=lambda _:guild,fetch_channel=AsyncMock(return_value=channel))
        return DiscordScheduleAdapter(bot),channel,guild

    def job(self, **values):
        return dict(id=5,guild_id=1,deadline=4_000_000_000,payload=dict(kind='message',channel_id=10,title='Generated',body='@everyone',color=0,**values))

    async def test_message_recovery_matches_bot_footer_only_and_never_resends(self):
        message=SimpleNamespace(id=88,author=SimpleNamespace(id=99),embeds=[discord.Embed().set_footer(text='Tueka schedule:5')])
        port,channel,_=self.setup_port([message])
        self.assertEqual(await port.deliver(self.job(),recover=True),88)
        channel.send.assert_not_awaited()
        message.author.id=100
        with self.assertRaises(DiscordFailure):await port.deliver(self.job(),recover=True)
        channel.send.assert_not_awaited()

    async def test_message_send_mentions_permissions_and_deadline(self):
        port,channel,_=self.setup_port()
        self.assertEqual(await port.deliver(self.job(),recover=False),44)
        self.assertEqual(channel.send.call_args.kwargs['allowed_mentions'].to_dict()['parse'],[])
        job=self.job();job['deadline']=0
        with self.assertRaises(DiscordFailure):await port.deliver(job,recover=False)
        channel.guild.id=2
        with self.assertRaises(DiscordFailure):await port.deliver(self.job(),recover=False)
        self.assertEqual(channel.send.await_count,1)

    async def test_external_event_creation_and_receipt_recovery(self):
        port,_,guild=self.setup_port()
        job=self.job();job['payload'].update(kind='event',event_start=3_000_000_000,event_end=3_000_000_100,event_location='Test venue')
        self.assertEqual(await port.deliver(job,recover=False),55)
        options=guild.create_scheduled_event.call_args.kwargs
        self.assertEqual(options['entity_type'],discord.EntityType.external)
        self.assertIsNotNone(options['start_time'].tzinfo)
        event=SimpleNamespace(id=66,creator_id=99,description=options['description'])
        guild.fetch_scheduled_events.return_value=[event]
        self.assertEqual(await port.deliver(job,recover=True),66)
        self.assertEqual(guild.create_scheduled_event.await_count,1)
        event.creator_id=1
        with self.assertRaises(DiscordFailure):await port.deliver(job,recover=True)
        self.assertEqual(guild.create_scheduled_event.await_count,1)
