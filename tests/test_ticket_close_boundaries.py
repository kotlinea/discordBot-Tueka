import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import httpx
from psycopg import IntegrityError
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from db_support import prepare_database
from dashboard.api_v1 import create_api_router
from dashboard.repository import DashboardRepository
from ticketing import TicketRepository, TicketService, TranscriptStorage
from cogs.community.tickets import TicketsCog
from jobs import LostLease
from jobs.leases import ResourceLease


class SimulatedCloseCrash(BaseException):
    """Bypass normal recovery without asyncio's special SystemExit shutdown."""


class TicketCloseBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = prepare_database(self.root / 'audit.db', self.addCleanup)
        key = Fernet.generate_key().decode()
        settings = SimpleNamespace(database_url=self.database, data_dir=self.root,
            ticket_encryption_key=key, reaction_role_max_mappings_per_message=20,
            **{f'ticket_s3_{k}': '' for k in ('endpoint_url', 'region', 'bucket', 'access_key_id', 'secret_access_key', 'prefix')})
        self.repo = TicketRepository(self.database)
        self.repo.save_settings(1, {'enabled': True, 'open_limit': 2})
        team = self.repo.save_team(1, {'name': 'Staff', 'role_ids': [500]})
        panel = self.repo.save_panel(1, {'name': 'Support', 'mode': 'private_thread',
            'thread_parent_channel_id': 100, 'staff_notification_channel_id': 101,
            'team_id': team['id']})
        self.storage = TranscriptStorage(self.root / 'ticket-transcripts', key)
        self.service = TicketService(self.repo, self.storage)
        ticket, _ = self.service.reserve(1, panel['id'], 10, 'audit-ticket', set())
        self.ticket = self.repo.activate_ticket(ticket['id'], 200, 100)
        DashboardRepository(self.database).create_dashboard_session('session', 'token', 3600)
        self.discord = SimpleNamespace(current_user=AsyncMock(return_value={'id': '10'}),
            can_manage=AsyncMock(return_value=False), guild_member=AsyncMock(return_value=None))
        app = FastAPI()
        @app.middleware('http')
        async def session(request, call_next):
            request.scope['session'] = {'session_id': 'session', 'csrf_token': 'csrf'}
            return await call_next(request)
        app.include_router(create_api_router(self.database, self.discord, settings))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_opener_cannot_read_private_note_but_assigned_staff_can(self):
        # Uses the real note delivery path for private threads (no Discord post).
        item = self.service.queue_reply(self.ticket['id'], 99, 'Private Staff Identity',
            'CONFIDENTIAL staff-only assessment', note=True)
        asyncio.run(self.service.deliver_message(SimpleNamespace(), self.ticket, item))
        _, transcript = asyncio.run(self.service.close(self.ticket['id'], 99, 'done'))
        response = self.client.get(f"/api/v1/tickets/transcripts/{transcript['id']}")
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual([], [m for m in response.json()['messages'] if m['kind'] == 'note'])
        self.assertNotIn('CONFIDENTIAL', response.text)
        self.assertNotIn('Private Staff Identity', response.text)
        self.discord.current_user.return_value = {'id': '99'}
        self.discord.guild_member.return_value = {'roles': ['500']}
        staff_response = self.client.get(f"/api/v1/tickets/transcripts/{transcript['id']}")
        self.assertEqual(200, staff_response.status_code, staff_response.text)
        note = next(m for m in staff_response.json()['messages'] if m['kind'] == 'note')
        self.assertEqual('CONFIDENTIAL staff-only assessment', note['content'])
        self.assertEqual('Private Staff Identity', note['author'])
        self.discord.current_user.return_value = {'id': '10'}
        staff_opener = self.client.get(f"/api/v1/tickets/transcripts/{transcript['id']}")
        self.assertEqual(200, staff_opener.status_code, staff_opener.text)
        self.assertTrue(any(m['kind'] == 'note' for m in staff_opener.json()['messages']))

    def test_opener_missing_guild_access_keeps_public_transcript_without_notes(self):
        item = self.service.queue_reply(self.ticket['id'], 99, 'Private Staff Identity', 'CONFIDENTIAL', note=True)
        asyncio.run(self.service.deliver_message(object(), self.ticket, item))
        _, transcript = asyncio.run(self.service.close(self.ticket['id'], 99, 'done'))
        for status in (403, 404):
            with self.subTest(upstream_status=status):
                request = httpx.Request('GET', 'https://discord.com/api/v10/guilds/1/members/10', headers={'Authorization': 'Bot test'})
                response = httpx.Response(status, request=request)
                self.discord.guild_member.side_effect = httpx.HTTPStatusError('Guild unavailable', request=request, response=response)
                result = self.client.get(f"/api/v1/tickets/transcripts/{transcript['id']}")
                self.assertEqual(200, result.status_code, result.text)
                self.assertNotIn('CONFIDENTIAL', result.text)
                self.assertNotIn('Private Staff Identity', result.text)

    def test_optional_staff_lookup_preserves_upstream_failure_contract(self):
        _, transcript = asyncio.run(self.service.close(self.ticket['id'], 99, 'done'))
        for status, authorization, expected in ((500, 'Bot test', 503), (429, 'Bot test', 503),
                                                (401, 'Bot test', 503), (401, 'Bearer test', 401)):
            with self.subTest(upstream_status=status, authorization=authorization):
                request = httpx.Request('GET', 'https://discord.com/api/v10/guilds/1/members/10', headers={'Authorization': authorization})
                response = httpx.Response(status, request=request)
                self.discord.guild_member.side_effect = httpx.HTTPStatusError('Upstream failed', request=request, response=response)
                result = self.client.get(f"/api/v1/tickets/transcripts/{transcript['id']}")
                self.assertEqual(expected, result.status_code, result.text)

    def test_expiring_old_version_preserves_unexpired_version_content(self):
        _, old = asyncio.run(self.service.close(self.ticket['id'], 99, 'first close'))
        reopened = self.repo.reopen_ticket(self.ticket['id'])
        self.service.record_message(reopened, 900, 10, 'opener', 'new conversation', [])
        stored = asyncio.run(self.storage.save_attachment(1, reopened['id'], 901, b'new attachment'))
        attachment = self.repo.save_attachment(reopened['id'], 901, 'new.txt', 'text/plain', 14,
            stored.backend, stored.object_key, stored.content_hash)
        _, new = asyncio.run(self.service.close(reopened['id'], 99, 'second close'))
        with self.repo._connection() as c:
            c.execute('UPDATE ticket_transcripts SET expires_at=%s WHERE id=%s', (int(time.time())-1, old['id']))
        cog = SimpleNamespace(repository=self.repo, transcripts=self.storage)
        asyncio.run(TicketsCog.maintain_transcripts.coro(cog))
        tr_response = self.client.get(f"/api/v1/tickets/transcripts/{new['id']}")
        at_response = self.client.get(f"/api/v1/tickets/attachments/{attachment['id']}")
        self.assertEqual(200, tr_response.status_code, tr_response.text)
        self.assertIn(attachment['id'], [a['id'] for a in tr_response.json()['attachments']])
        self.assertEqual(200, at_response.status_code, at_response.text)
        self.assertEqual('new conversation', self.storage.decrypt_text(self.repo.messages(reopened['id'])[0]['encrypted_content']))

    def test_expiring_old_version_preserves_reopened_conversation(self):
        _, old = asyncio.run(self.service.close(self.ticket['id'], 99, 'first close'))
        reopened = self.repo.reopen_ticket(self.ticket['id'])
        self.service.record_message(reopened, 900, 10, 'opener', 'active conversation', [])
        stored = asyncio.run(self.storage.save_attachment(1, reopened['id'], 901, b'active file'))
        attachment = self.repo.save_attachment(reopened['id'], 901, 'active.txt', 'text/plain', 11,
            stored.backend, stored.object_key, stored.content_hash)
        with self.repo._connection() as c:
            c.execute('UPDATE ticket_transcripts SET expires_at=%s WHERE id=%s', (int(time.time())-1, old['id']))
        asyncio.run(TicketsCog.maintain_transcripts.coro(SimpleNamespace(repository=self.repo, transcripts=self.storage)))
        self.assertEqual('active conversation', self.storage.decrypt_text(self.repo.messages(reopened['id'])[0]['encrypted_content']))
        response = self.client.get(f"/api/v1/tickets/attachments/{attachment['id']}")
        self.assertEqual(200, response.status_code, response.text)

    def test_final_transcript_expiration_still_purges_closed_ticket_content(self):
        self.service.record_message(self.ticket, 900, 10, 'opener', 'expired conversation', [])
        stored = asyncio.run(self.storage.save_attachment(1, self.ticket['id'], 901, b'expired file'))
        attachment = self.repo.save_attachment(self.ticket['id'], 901, 'expired.txt', 'text/plain', 12,
            stored.backend, stored.object_key, stored.content_hash)
        _, transcript = asyncio.run(self.service.close(self.ticket['id'], 99, 'done'))
        with self.repo._connection() as c:
            c.execute('UPDATE ticket_transcripts SET expires_at=%s WHERE id=%s', (int(time.time())-1, transcript['id']))
        asyncio.run(TicketsCog.maintain_transcripts.coro(SimpleNamespace(repository=self.repo, transcripts=self.storage)))
        self.assertEqual('', self.storage.decrypt_text(self.repo.messages(self.ticket['id'])[0]['encrypted_content']))
        self.assertFalse((self.root / 'ticket-transcripts' / stored.object_key).exists())
        self.assertEqual(404, self.client.get(f"/api/v1/tickets/attachments/{attachment['id']}").status_code)

    def test_failed_attachment_purge_is_retried_without_restoring_download_access(self):
        stored = asyncio.run(self.storage.save_attachment(1, self.ticket['id'], 901, b'expired file'))
        attachment = self.repo.save_attachment(self.ticket['id'], 901, 'expired.txt', 'text/plain', 12,
            stored.backend, stored.object_key, stored.content_hash)
        _, transcript = asyncio.run(self.service.close(self.ticket['id'], 99, 'done'))
        with self.repo._connection() as c:
            c.execute('UPDATE ticket_transcripts SET expires_at=%s WHERE id=%s', (int(time.time())-1, transcript['id']))
        cog = SimpleNamespace(repository=self.repo, transcripts=self.storage)
        with patch.object(self.storage, 'delete', side_effect=OSError('temporary storage failure')):
            asyncio.run(TicketsCog.maintain_transcripts.coro(cog))
        self.assertEqual('purging', self.repo.attachment(attachment['id'])['status'])
        self.assertEqual('ready', self.repo.transcript(transcript['id'])['status'])
        self.assertEqual(404, self.client.get(f"/api/v1/tickets/attachments/{attachment['id']}").status_code)
        asyncio.run(TicketsCog.maintain_transcripts.coro(cog))
        self.assertEqual('deleted', self.repo.attachment(attachment['id'])['status'])
        self.assertEqual('deleted', self.repo.transcript(transcript['id'])['status'])
        self.assertFalse((self.root / 'ticket-transcripts' / stored.object_key).exists())

    def test_reopen_during_external_purge_keeps_new_conversation_and_attachment(self):
        stored = asyncio.run(self.storage.save_attachment(1, self.ticket['id'], 901, b'expired file'))
        self.repo.save_attachment(self.ticket['id'], 901, 'expired.txt', 'text/plain', 12,
            stored.backend, stored.object_key, stored.content_hash)
        _, transcript = asyncio.run(self.service.close(self.ticket['id'], 99, 'done'))
        with self.repo._connection() as c:
            c.execute('UPDATE ticket_transcripts SET expires_at=%s WHERE id=%s', (int(time.time())-1, transcript['id']))
        delete = self.storage.delete
        new = {}
        async def delete_after_reopen(backend, object_key):
            if not new:
                reopened = self.repo.reopen_ticket(self.ticket['id'])
                self.service.record_message(reopened, 950, 10, 'opener', 'new after purge started', [])
                blob = await self.storage.save_attachment(1, reopened['id'], 951, b'new file')
                new['attachment'] = self.repo.save_attachment(reopened['id'], 951, 'new.txt', 'text/plain', 8,
                    blob.backend, blob.object_key, blob.content_hash)
                _, new['transcript'] = await self.service.close(reopened['id'], 99, 'new close')
            await delete(backend, object_key)
        with patch.object(self.storage, 'delete', side_effect=delete_after_reopen):
            asyncio.run(TicketsCog.maintain_transcripts.coro(SimpleNamespace(repository=self.repo, transcripts=self.storage)))
        response = self.client.get(f"/api/v1/tickets/transcripts/{new['transcript']['id']}")
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual([new['attachment']['id']], [a['id'] for a in response.json()['attachments']])
        self.assertEqual(200, self.client.get(f"/api/v1/tickets/attachments/{new['attachment']['id']}").status_code)
        self.assertEqual('new after purge started', self.storage.decrypt_text(self.repo.messages(self.ticket['id'])[0]['encrypted_content']))

    def test_restart_between_transcript_and_close_restores_jobs_once(self):
        with patch.object(self.repo, 'close_ticket', side_effect=SimulatedCloseCrash('simulated process crash')):
            with self.assertRaises(SimulatedCloseCrash):
                asyncio.run(self.service.close(self.ticket['id'], 99, 'done'))
        self.assertEqual('closing', self.repo.ticket(self.ticket['id'])['status'])
        self.assertIsNotNone(self.repo.transcript_for_ticket(self.ticket['id']))
        with patch('ticketing.repository.time.time', return_value=time.time()+301):
            restarted = TicketRepository(self.database)
        self.assertEqual('closed', restarted.ticket(self.ticket['id'])['status'])
        actions = [row['action'] for row in restarted.outbox(self.ticket['id'])]
        self.assertCountEqual(['close_resource', 'close_dm', 'close_log'], actions)
        restarted.recover_incomplete_closes()
        repeated = TicketRepository(self.database)
        self.assertCountEqual(actions, [row['action'] for row in repeated.outbox(self.ticket['id'])])

    def test_fast_restart_recovers_on_periodic_tick_after_cutoff(self):
        with patch.object(self.repo, 'close_ticket', side_effect=SimulatedCloseCrash('crash after snapshot')):
            with self.assertRaises(SimulatedCloseCrash):
                asyncio.run(self.service.close(self.ticket['id'], 99, 'done'))
        started = self.repo.ticket(self.ticket['id'])['closing_at']
        with patch('ticketing.repository.time.time', return_value=started + 1):
            restarted = TicketRepository(self.database)
        self.assertEqual('closing', restarted.ticket(self.ticket['id'])['status'])
        cog = SimpleNamespace(repository=restarted, owner='restart-test', _expire_ticket_schedule=lambda item: None)
        with patch('ticketing.repository.time.time', return_value=started + 301):
            asyncio.run(TicketsCog.auto_close.coro(cog))
        self.assertEqual('closed', restarted.ticket(self.ticket['id'])['status'])
        self.assertCountEqual(['close_resource', 'close_dm', 'close_log'], [r['action'] for r in restarted.outbox(self.ticket['id'])])

    def test_active_close_lease_prevents_recovery_after_five_minutes(self):
        clock = [int(time.time())]
        original_save = self.storage.save
        async def slow_save(*args):
            clock[0] += 301
            self.repo.recover_incomplete_closes()
            self.assertEqual('closing', self.repo.ticket(self.ticket['id'])['status'])
            return await original_save(*args)
        def lease(database, namespace, key):
            return ResourceLease(database, namespace, key, seconds=600, clock=lambda: clock[0])
        with patch('ticketing.service.ResourceLease', side_effect=lease), patch('ticketing.repository.time.time', side_effect=lambda: clock[0]):
            with patch.object(self.storage, 'save', side_effect=slow_save):
                closed, _ = asyncio.run(self.service.close(self.ticket['id'], 99, 'done'))
        self.assertEqual('closed', closed['status'])

    def test_expired_close_writer_cannot_save_snapshot_or_cancel_new_state(self):
        clock = [int(time.time())]
        original_save = self.storage.save
        async def stale_save(*args):
            clock[0] += 301
            self.repo.recover_incomplete_closes()
            self.assertEqual('open', self.repo.ticket(self.ticket['id'])['status'])
            return await original_save(*args)
        def lease(database, namespace, key):
            return ResourceLease(database, namespace, key, seconds=60, clock=lambda: clock[0])
        with patch('ticketing.service.ResourceLease', side_effect=lease), patch('ticketing.repository.time.time', side_effect=lambda: clock[0]):
            with patch.object(self.storage, 'save', side_effect=stale_save):
                with self.assertRaises(LostLease):
                    asyncio.run(self.service.close(self.ticket['id'], 99, 'done'))
        self.assertIsNone(self.repo.transcript_for_ticket(self.ticket['id']))
        self.assertEqual('open', self.repo.ticket(self.ticket['id'])['status'])

    def test_expired_close_owner_cannot_complete_or_cancel(self):
        clock = [int(time.time())]
        old = ResourceLease(self.database, 'ticket_close', self.ticket['id'], clock=lambda: clock[0])
        old.acquire()
        self.addCleanup(old.release)
        self.repo.begin_close(self.ticket['id'], 99, 'done')
        clock[0] += 61
        current = ResourceLease(self.database, 'ticket_close', self.ticket['id'], clock=lambda: clock[0])
        current.acquire()
        self.addCleanup(current.release)
        for operation in (lambda: self.repo.close_ticket(self.ticket['id'], 99, 'done', lease=old),
                          lambda: self.repo.cancel_close(self.ticket['id'], lease=old)):
            with self.assertRaises(LostLease):
                operation()
        self.assertEqual('closing', self.repo.ticket(self.ticket['id'])['status'])
        self.assertEqual([], self.repo.outbox(self.ticket['id']))

    def test_reopened_close_crash_cannot_reuse_previous_cycle_transcript(self):
        asyncio.run(self.service.close(self.ticket['id'], 99, 'first close'))
        self.repo.reopen_ticket(self.ticket['id'])
        before = self.repo.outbox(self.ticket['id'])
        with patch.object(self.storage, 'save', side_effect=SimulatedCloseCrash('crash before new snapshot')):
            with self.assertRaises(SimulatedCloseCrash):
                asyncio.run(self.service.close(self.ticket['id'], 99, 'second close'))
        with patch('ticketing.repository.time.time', return_value=time.time()+301):
            restarted = TicketRepository(self.database)
        self.assertEqual('open', restarted.ticket(self.ticket['id'])['status'])
        self.assertEqual(before, restarted.outbox(self.ticket['id']))

    def test_transcript_attachment_assigned_team_and_deleted_resource_access(self):
        stored = asyncio.run(self.storage.save_attachment(1, self.ticket['id'], 950, b'file'))
        attachment = self.repo.save_attachment(self.ticket['id'], 950, 'file.txt', 'text/plain', 4,
            stored.backend, stored.object_key, stored.content_hash)
        _, transcript = asyncio.run(self.service.close(self.ticket['id'], 99, 'done'))
        urls = [f"/api/v1/tickets/transcripts/{transcript['id']}",
                f"/api/v1/tickets/attachments/{attachment['id']}"]
        self.repo.save_team(1, {'name': 'Other team', 'role_ids': [600]})
        self.discord.current_user.return_value = {'id': '30'}
        self.discord.guild_member.return_value = {'roles': ['600']}
        for url in urls:
            self.assertEqual(403, self.client.get(url).status_code)
        self.discord.guild_member.return_value = None
        for url in urls:
            self.assertEqual(403, self.client.get(url).status_code)
        self.repo.mark_deleted(self.ticket['id'], int(time.time()))
        self.discord.current_user.return_value = {'id': '10'}
        for url in urls:
            self.assertEqual(200, self.client.get(url).status_code)

    def test_duplicate_feedback_is_prevented_under_synchronized_submissions(self):
        asyncio.run(self.service.close(self.ticket['id'], 99, 'done'))
        gate = Barrier(2)
        def submit():
            gate.wait(timeout=10)
            try:
                self.repo.save_feedback(self.ticket['id'], 10, 5)
                return 'saved'
            except IntegrityError:
                return 'duplicate'
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(submit) for _ in range(2)]
            outcomes = [f.result(timeout=20) for f in futures]
        self.assertCountEqual(['saved', 'duplicate'], outcomes)


if __name__ == '__main__':
    unittest.main(verbosity=2)
