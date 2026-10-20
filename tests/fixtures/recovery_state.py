"""Real stored ciphertext and queue receipts; no Discord/provider network calls."""
import asyncio
import json
import time

from config import Settings
from database import transaction
from guild_settings import GuildSettingsRepository
from jobs import Outcome, run_batch
from recovery.storage import storage, verify
from social import SocialRepository
from social.crypto import SocialTokenCipher
from suggestions import SuggestionRepository
from suggestions.delivery import SuggestionDeliveryService
from ticketing import TicketRepository
from applications.repository import ApplicationRepository
from appeals.repository import AppealRepository
from appeals.delivery import AppealDeliveryService
from scheduling.repository import ScheduleRepository
from scheduling.delivery import ScheduleDeliveryService
from starboard.repository import StarboardRepository
from starboard.delivery import HighlightDelivery
from giveaways.repository import GiveawayRepository
from giveaways.service import GiveawayService
from insights.repository import InsightsRepository
from insights.models import day_key


async def seed():
    settings = Settings.from_env()
    store = storage(settings)
    repo = TicketRepository(settings.database_url)
    repo.save_settings(1, {'enabled': True})
    team = repo.save_team(1, {'name': 'Staff', 'role_ids': [50]})
    panel = repo.save_panel(1, {'name': 'Recovery', 'mode': 'channel', 'category_id': 10, 'team_id': team['id']})
    ticket = repo.reserve_ticket(1, panel['id'], 2, 'recovery-test', {'answer': store.encrypt_text('private answer')})
    blob = await store.save(1, ticket['id'], {'body': 'private transcript'})
    repo.save_transcript(ticket['id'], blob.backend, blob.object_key, blob.content_hash, blob.byte_size, 9999999999)
    attachment = await store.save_attachment(1, ticket['id'], 99, b'private attachment')
    repo.save_attachment(ticket['id'], 99, 'proof.txt', 'text/plain', attachment.byte_size,
        attachment.backend, attachment.object_key, attachment.content_hash)
    cipher = SocialTokenCipher(settings.social_token_encryption_key)
    SocialRepository(settings.database_url).save_social_connection(1, 'twitch', 'offline', 'Offline', cipher.encrypt('private access'), cipher.encrypt('private refresh'), 9999999999)
    guilds = GuildSettingsRepository(settings.database_url)
    insight_now = int(time.time()) - 20
    insights = InsightsRepository(settings.database_url, clock=lambda: insight_now)
    guilds.set_module(1, 'insights', enabled=True, settings={'channel_ids': [10], 'retention_days': 30, 'track_members': True})
    assert insights.claim(1, 'before-snapshot-observer')
    insights.heartbeat(1, 'before-snapshot-observer', {30: 10})
    assert insights.event(1, 'before-snapshot-observer', 'messages', 'generated-recovery-message', channel=10)
    insight_now += 10
    insights.heartbeat(1, 'before-snapshot-observer', {30: 10})
    with transaction(settings.database_url) as c:
        c.execute("INSERT INTO app_metadata(key,value) VALUES('insights_snapshot_time',%s)", (str(insight_now),))
    guilds.set_module(1, 'applications', enabled=True)
    applications = ApplicationRepository(settings.database_url)
    form = applications.save_form(1, 5, {'title':'Recovery application','enabled':True,'fields':[{'key':'answer','label':'Answer'}]})
    application = applications.submit(1,form['id'],3,987654321,{'answer':'Snapshot answer'},revision=1,roles=[],created_at=1,joined_at=1)
    applications.transition(1,application['id'],5,'approved','Snapshot decision',revision=1)
    guilds.set_module(1, 'appeals', enabled=True)
    appeals = AppealRepository(settings.database_url)
    mail = appeals.open(1,3,987654322,'Private restored ModMail',application_id=application['id'])
    appeals.reply(1,mail['id'],5,'Private restored reply',revision=1,staff=True)
    pending_dm = appeals.jobs.claim('crashed-mail-worker')
    assert appeals.delivery_state(pending_dm.payload)
    with transaction(settings.database_url) as c:
        c.execute('UPDATE appeal_outbox SET lease_until=0 WHERE id=%s',(pending_dm.id,))
    guilds.set_module(1, 'suggestions', enabled=True, settings={})
    guilds.set_module(1, 'scheduled_messages', enabled=True)
    instant=int(time.time())
    schedules=ScheduleRepository(settings.database_url,clock=lambda:instant)
    post=schedules.create(1,5,{'kind':'message','title':'Restored schedule','body':'Scheduled restore body','channel_id':2,'run_at':instant+30},'recovery-schedule')
    instant+=30
    schedules.enqueue_due()
    scheduled=schedules.jobs.claim('crashed-schedule-worker')
    assert schedules.start_delivery(scheduled.payload)=='send'
    with transaction(settings.database_url) as c:
        c.execute('UPDATE scheduled_post_outbox SET lease_until=0,available_at=0 WHERE id=%s',(scheduled.id,))
    guilds.set_module(1,'starboard',enabled=True)
    highlights=StarboardRepository(settings.database_url)
    board=highlights.save_board(1,5,{'name':'Recovery highlights','enabled':True,'target_channel_id':2,'source_channel_ids':[10],'threshold':2},request_key='recovery-highlight-board')
    source={'guild_id':1,'channel_id':10,'message_id':778,'parent_channel_id':None,'author_id':3,'author_bot':False,'author_name':'Restored author','content':'Restored highlight body','nsfw':False,'deleted':False,'image_url':''}
    highlights.observe(1,board['id'],1,source,2)
    uncertain=highlights.jobs.claim('crashed-highlight-worker')
    publication,action=highlights.publication_begin(uncertain.payload,2)
    assert action=='send'
    highlights.enqueue_refresh(1,10,778)
    with transaction(settings.database_url) as c:
        c.execute('UPDATE starboard_outbox SET lease_until=0,available_at=0 WHERE id=%s',(uncertain.id,))
    guilds.set_module(1, 'giveaways', enabled=True)
    campaigns = GiveawayRepository(settings.database_url)
    registration = campaigns.create(1, 5, {'title': 'Restored uncertain campaign', 'channel_id': 2, 'ends_at': instant + 3600}, 'recovery-uncertain')
    registration = campaigns.launch(1, registration['id'], 5, registration['revision'])
    unknown = campaigns.jobs.claim('crashed-campaign-publication')
    assert campaigns.publication_begin(unknown.payload) == 'send'
    completed = campaigns.create(1, 5, {'title': 'Restored draw history', 'channel_id': 2, 'ends_at': instant + 3600}, 'recovery-draw')
    completed = campaigns.launch(1, completed['id'], 5, completed['revision'])
    receipt = campaigns.jobs.claim('known-campaign-publication')
    assert receipt.payload['campaign_id'] == completed['id']
    campaigns.publication_begin(receipt.payload)
    campaigns.publication_receipt(receipt.payload, 888)
    assert campaigns.jobs.finish(receipt, Outcome())
    for user in (30, 31):
        campaigns.enter(1, completed['id'], user, 888, 987660000 + user, join=True)
    completed = campaigns.item(1, completed['id'])
    campaigns.close(1, completed['id'], 5, completed['revision'], 'Recovery early close')
    draw = campaigns.draw_jobs.claim('crashed-draw-commit')
    plan = campaigns.draw_plan(draw.payload)
    import random
    campaigns.complete_draw(draw.payload, plan['campaign']['revision'], [30, 31], rng=random.Random(1))
    completed = campaigns.item(1, completed['id'])
    campaigns.reroll(1, completed['id'], 5, completed['revision'], 'Recovery reroll')
    with transaction(settings.database_url) as c:
        c.execute('UPDATE giveaway_outbox SET lease_until=0,available_at=0 WHERE id=%s', (unknown.id,))
        c.execute('UPDATE giveaway_draw_jobs SET lease_until=0,available_at=0 WHERE id=%s', (draw.id,))
    suggestions = SuggestionRepository(settings.database_url)
    delivered = suggestions.create(1, 2, 3, {'idea': 'already delivered'})
    claim = suggestions.outbox_jobs.claim('before-snapshot')
    suggestions.publication_delivered(claim.payload, 111)
    assert suggestions.outbox_jobs.finish(claim, Outcome())
    sync = suggestions.outbox_jobs.claim('before-snapshot-sync')
    assert sync.payload['action'] == 'sync'
    assert suggestions.outbox_jobs.finish(sync, Outcome())
    approved = suggestions.review(1, delivered['id'], 5, 'approved', 'Accepted for recovery test')
    suggestions.review(1, delivered['id'], 5, 'implemented', 'Recovery implementation proof', expected_revision=approved['revision'])
    # A known completed remote discussion receipt, scoped to the published message.
    with transaction(settings.database_url) as c:
        c.execute('UPDATE suggestions SET discussion_thread_id=111 WHERE id=%s', (delivered['id'],))
    while receipt := suggestions.outbox_jobs.claim('completed-review-receipts'):
        assert receipt.payload['action'] in {'sync', 'review_log'}
        assert suggestions.outbox_jobs.finish(receipt, Outcome())
    pending = suggestions.create(1, 2, 4, {'idea': 'uncertain delivery'})
    claim = suggestions.outbox_jobs.claim('crashed-worker')
    assert claim.payload['action'] == 'publish' and claim.payload['suggestion_id'] == pending['id']
    suggestions.delivery_state(claim.payload, started=True)
    guilds.set_module(1,'suggestions',enabled=True,settings={'categories':['Recovery'],'tags':['Snapshot']})
    duplicate=suggestions.create(1,2,6,{'idea':'Restored duplicate'})
    suggestions.attach_message(1,duplicate['id'],333)
    suggestions.vote(1,duplicate['id'],31,1)
    suggestions.vote(1,duplicate['id'],32,-1)
    canonical=suggestions.get(1,delivered['id'])
    canonical=suggestions.set_labels(1,canonical['id'],5,'Recovery',['Snapshot'],canonical['revision'])
    duplicate=suggestions.get(1,duplicate['id'])
    suggestions.merge(1,duplicate['id'],canonical['id'],5,'Recovery duplicate proof',duplicate['revision'],canonical['revision'])
    with transaction(settings.database_url) as c:
        # Simulated, already known original receipt; leave only the existing uncertain job pending.
        c.execute("UPDATE suggestion_outbox SET status='completed',completed_at=%s WHERE suggestion_id=ANY(%s) AND status='pending'",(int(time.time()),[duplicate['id'],canonical['id']]))
        c.execute('INSERT INTO suggestion_votes(suggestion_id,user_id,value,created_at,updated_at) VALUES(%s,31,0,%s,%s)',(canonical['id'],int(time.time()),int(time.time())))
        c.execute("UPDATE suggestion_outbox SET lease_until=0 WHERE suggestion_id=%s", (pending['id'],))
        c.execute("INSERT INTO app_metadata VALUES('recovery_version','old')")
    print(json.dumps(await verify(settings)))


async def resume():
    settings = Settings.from_env()
    repository = SuggestionRepository(settings.database_url)
    applications = ApplicationRepository(settings.database_url)
    application = applications.items(1)[0]
    assert application['snapshot']['title'] == 'Recovery application'
    assert application['answers'] == {'answer':'Snapshot answer'} and application['status'] == 'approved'
    assert applications.events(1,application['id'])[0]['reason'] == 'Snapshot decision'
    assert applications.form(1,application['form_id'])['retention_days'] == 30
    with transaction(settings.database_url) as c:
        cooldown = c.execute('SELECT submitted_at FROM application_cooldowns WHERE guild_id=1 AND form_id=%s AND author_id=3', (application['form_id'],)).fetchone()
        assert cooldown and cooldown['submitted_at'] == application['created_at']
    appeals = AppealRepository(settings.database_url)
    mail = appeals.items(1)[0]
    detail = appeals.conversation(1,mail['id'])
    assert [m['content'] for m in detail['messages']] == ['Private restored ModMail','Private restored reply']
    assert mail['application_id'] == application['id']
    class ExistingDmReceipt:
        calls=0
        async def notify(self,item,key,*,recover):
            assert recover and item['body'] == 'Private restored reply'
            self.calls+=1
            return 444
    dm = ExistingDmReceipt()
    assert await run_batch(appeals.jobs,'restored-mail-worker',AppealDeliveryService(appeals,dm).deliver) == 1
    assert await run_batch(appeals.jobs,'restored-mail-worker',AppealDeliveryService(appeals,dm).deliver) == 0
    assert dm.calls == 1
    assert appeals.conversation(1,mail['id'])['delivery'][0]['discord_message_id'] == 444
    schedules=ScheduleRepository(settings.database_url)
    post=schedules.items(1)[0]
    assert json.loads(post['payload_json'])['body']=='Scheduled restore body'
    class ExistingScheduleReceipt:
        calls=0
        async def deliver(self,job,*,recover):
            assert recover and job['payload']['title']=='Restored schedule'
            self.calls+=1
            return 555
    schedule_port=ExistingScheduleReceipt()
    assert await run_batch(schedules.jobs,'restored-schedule-worker',ScheduleDeliveryService(schedules,schedule_port).deliver)==1
    assert await run_batch(schedules.jobs,'restored-schedule-worker',ScheduleDeliveryService(schedules,schedule_port).deliver)==0
    assert schedule_port.calls==1
    assert schedules.history(1,post['id'])['delivery'][0]['discord_receipt_id']==555

    highlights=StarboardRepository(settings.database_url)
    restored_board=highlights.boards(1)[0]
    restored_source=highlights.entries(1,restored_board['id'])[0]['snapshot']
    assert restored_source['content']=='Restored highlight body'
    class ExistingHighlightReceipt:
        reconciled=0
        edited=0
        async def source(self,*_):return restored_source,2
        async def reconcile(self,guild,channel,marker):
            assert guild==1 and channel==2 and marker.startswith('Tueka highlight:')
            self.reconciled+=1;return 666
        async def edit(self,guild,channel,message,*_):
            assert message==666;self.edited+=1
        async def send(self,*_):raise AssertionError('Uncertain restored highlight must not be resent')
        async def delete(self,*_):raise AssertionError('Restored highlight remains eligible')
    highlight_port=ExistingHighlightReceipt()
    assert await run_batch(highlights.jobs,'restored-highlight-worker',HighlightDelivery(highlights,highlight_port).handle)==1
    assert await run_batch(highlights.jobs,'restored-highlight-worker',HighlightDelivery(highlights,highlight_port).handle)==0
    assert (highlight_port.reconciled,highlight_port.edited)==(1,1)
    assert highlights.delivery_history(1,restored_board['id'])['publications'][0]['message_id']==666
    source_job=highlights.refresh_jobs.claim('restored-highlight-source')
    assert source_job.payload['channel_id']==10 and source_job.payload['message_id']==778
    assert highlights.refresh_jobs.finish(source_job,Outcome())

    campaigns = GiveawayRepository(settings.database_url)
    class ExistingCampaignReceipts:
        reconciled = 0
        edited = []
        async def member(self, guild, user):
            return {'id': user, 'guild_id': guild, 'bot': False, 'role_ids': [], 'created_at': 1, 'joined_at': 1}
        async def reconcile(self, guild, channel, marker):
            assert guild == 1 and channel == 2 and marker.startswith('Tueka campaign:')
            self.reconciled += 1
            return 777
        async def send(self, *_):
            raise AssertionError('Restored campaign must not be blindly republished')
        async def edit(self, plan, receipt, marker):
            self.edited.append(receipt)
    campaign_port = ExistingCampaignReceipts()
    campaign_service = GiveawayService(campaigns, campaign_port)
    assert await run_batch(campaigns.draw_jobs, 'restored-campaign-draw', campaign_service.draw) == 2
    assert await run_batch(campaigns.draw_jobs, 'restored-campaign-draw', campaign_service.draw) == 0
    restored_campaign = next(row for row in campaigns.items(1) if row['config']['title'] == 'Restored draw history')
    draws = campaigns.history(1, restored_campaign['id'])['draws']
    assert [json.loads(row['winners_json']) for row in draws] == [[30], [31]]
    assert await run_batch(campaigns.jobs, 'restored-campaign-publication', campaign_service.publish) == 2
    assert await run_batch(campaigns.jobs, 'restored-campaign-publication', campaign_service.publish) == 0
    assert campaign_port.reconciled == 1 and sorted(campaign_port.edited) == [777, 888]
    with transaction(settings.database_url) as c:
        insight_snapshot = int(c.execute("SELECT value FROM app_metadata WHERE key='insights_snapshot_time'").fetchone()['value'])
    insight_now = insight_snapshot + 91
    insights = InsightsRepository(settings.database_url, clock=lambda: insight_now)
    assert insights.claim(1, 'restored-observer')
    insights.heartbeat(1, 'restored-observer', {30: 10})
    assert not insights.event(1, 'restored-observer', 'messages', 'generated-recovery-message', channel=10)
    insight_now += 10
    insights.heartbeat(1, 'restored-observer', {30: 10})
    observed = insights.report(1, day_key(insight_snapshot - 10), day_key(insight_now))
    assert sum(day['messages'] or 0 for day in observed['days']) == 1
    assert sum(day['voice_seconds'] or 0 for day in observed['days']) == 20
    assert sum(day['observed_seconds'] or 0 for day in observed['days']) == 20

    class ExistingRemoteReceipt:
        calls = 0
        async def publish(self, item, settings, *, recover):
            assert recover, 'Uncertain delivery must use receipt reconciliation'
            self.calls += 1
            return 222  # A message that already exists in the simulated Discord port.

        async def sync(self, item, settings):
            assert item['message_id'] == 222

    port = ExistingRemoteReceipt()
    service = SuggestionDeliveryService(repository, GuildSettingsRepository(settings.database_url), port)
    assert await run_batch(repository.outbox_jobs, 'restored-worker', service.deliver) == 2
    assert await run_batch(repository.outbox_jobs, 'restored-worker', service.deliver) == 0
    assert port.calls == 1
    with transaction(settings.database_url) as c:
        assert [row['message_id'] for row in c.execute('SELECT message_id FROM suggestions ORDER BY id')] == [111, 222, 333]
        canonical=c.execute("SELECT id,category,tags_json FROM suggestions WHERE message_id=111").fetchone()
        duplicate=c.execute("SELECT id,merged_into,status FROM suggestions WHERE message_id=333").fetchone()
        assert canonical['category']=='Recovery' and json.loads(canonical['tags_json'])==['Snapshot']
        assert duplicate['merged_into']==canonical['id'] and duplicate['status']=='merged'
        assert repository.get(1,canonical['id'])['upvotes']==0 and repository.get(1,canonical['id'])['downvotes']==1
        assert c.execute('SELECT count(*) AS n FROM suggestion_votes WHERE suggestion_id=%s',(duplicate['id'],)).fetchone()['n']==2
        assert c.execute("SELECT count(*) AS n FROM suggestion_events WHERE event_type='merged'").fetchone()['n']==1
        reviewed = c.execute('SELECT status,review_reason,discussion_thread_id,implemented_at FROM suggestions WHERE message_id=111').fetchone()
        assert reviewed['status'] == 'implemented' and reviewed['review_reason'] == 'Recovery implementation proof'
        assert reviewed['discussion_thread_id'] == 111 and reviewed['implemented_at'] is not None
        assert c.execute("SELECT COUNT(*) AS n FROM suggestion_events WHERE event_type='status_changed'").fetchone()['n'] == 2
        assert c.execute("SELECT value FROM app_metadata WHERE key='recovery_version'").fetchone()['value'] == 'old'
    print('preserved receipt, uncertain delivery reconciliation, no duplicate delivery: OK')
