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
