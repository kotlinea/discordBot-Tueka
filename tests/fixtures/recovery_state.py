"""Real stored ciphertext and queue receipts; no Discord/provider network calls."""
import asyncio
import json

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


async def seed():
    settings = Settings.from_env()
    store = storage(settings)
    repo = TicketRepository(settings.database_url)
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
    with transaction(settings.database_url) as c:
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
        assert [row['message_id'] for row in c.execute('SELECT message_id FROM suggestions ORDER BY id')] == [111, 222]
        reviewed = c.execute('SELECT status,review_reason,discussion_thread_id,implemented_at FROM suggestions WHERE message_id=111').fetchone()
        assert reviewed['status'] == 'implemented' and reviewed['review_reason'] == 'Recovery implementation proof'
        assert reviewed['discussion_thread_id'] == 111 and reviewed['implemented_at'] is not None
        assert c.execute("SELECT COUNT(*) AS n FROM suggestion_events WHERE event_type='status_changed'").fetchone()['n'] == 2
        assert c.execute("SELECT value FROM app_metadata WHERE key='recovery_version'").fetchone()['value'] == 'old'
    print('preserved receipt, uncertain delivery reconciliation, no duplicate delivery: OK')
