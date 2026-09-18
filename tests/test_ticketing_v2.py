from db_support import prepare_database
import asyncio
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest.mock import patch, AsyncMock

from cryptography.fernet import Fernet

from ticketing import TicketRepository, TicketService, TicketValidationError, TranscriptStorage, validate_form, validate_panel
from ticketing.models import support_is_open
from ticketing.contracts import ContainerRef
from discord_io import DiscordFailure


class TicketV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository = TicketRepository(prepare_database(self.root / "tickets.db", self.addCleanup))
        self.storage = TranscriptStorage(self.root / "blobs", Fernet.generate_key().decode("ascii"))
        self.service = TicketService(self.repository, self.storage)
        self.repository.save_settings(1, {"enabled": True, "open_limit": 1})
        self.team = self.repository.save_team(1, {"name": "Staff", "role_ids": [500]})
        self.panel = self.repository.save_panel(1, {"name": "Support", "mode": "channel", "category_id": 100, "team_id": self.team["id"]})

    def tearDown(self):
        self.temp.cleanup()

    def test_welcome_recovers_after_receipt_save_failure_and_keeps_one_followup(self):
        class Port:
            created = 0
            async def create_container(self, *args):
                return ContainerRef(700, 100)
            async def member_identity(self, ticket):
                return {'id': 10, 'name': 'Member'}
            async def notice(self, ticket, key, packet, *, recover):
                if not recover:
                    self.created += 1
                return {'id': 900, 'created_at': 1000}
        ticket, panel = self.service.reserve(1, self.panel['id'], 10, 'welcome-retry', set())
        port = Port()
        ticket, _ = asyncio.run(self.service.open_container(port, ticket, panel, 'ticket'))
        item = self.repository.outbox_jobs.claim('worker').payload
        self.assertEqual(item['action'], 'welcome')
        with patch.object(self.repository, 'panel', return_value={**panel, 'remove_mentions': True}):
            with patch.object(self.repository, 'finish_notice', side_effect=RuntimeError('database failed')):
                with self.assertRaises(RuntimeError):
                    asyncio.run(self.service.deliver_notice(port, ticket, item, ''))
            asyncio.run(self.service.deliver_notice(port, ticket, item, ''))
            asyncio.run(self.service.deliver_notice(port, ticket, item, ''))
        self.assertEqual(port.created, 1)
        self.assertEqual([row['action'] for row in self.repository.outbox(ticket['id'])].count('remove_open_mentions'), 1)
        self.assertEqual(len(self.repository.messages(ticket['id'])), 1)

    def test_repeated_open_reuses_container_and_unknown_creation_can_reconcile(self):
        class Port:
            created = 0
            async def create_container(self, *args):
                self.created += 1
                return ContainerRef(700, 100)
            async def find_container(self, *args):
                return ContainerRef(700, 100)
        ticket, panel = self.service.reserve(1, self.panel['id'], 10, 'creation-retry', set())
        port = Port()
        opened, _ = asyncio.run(self.service.open_container(port, ticket, panel, 'ticket'))
        repeated, _ = asyncio.run(self.service.open_container(port, ticket, panel, 'ticket'))
        self.assertEqual(port.created, 1)
        self.assertEqual(repeated['discord_container_id'], opened['discord_container_id'])

    def test_unknown_creation_result_is_recovered_from_durable_intent(self):
        class Port:
            async def create_container(self, *args):
                raise DiscordFailure('response lost', partial=True)
            async def find_container(self, *args):
                return ContainerRef(701, 100)
        ticket, panel = self.service.reserve(1, self.panel['id'], 10, 'creation-unknown', set())
        port = Port()
        with self.assertRaises(DiscordFailure):
            asyncio.run(self.service.open_container(port, ticket, panel, 'ticket'))
        pending = self.repository.pending_container_creations(1)
        self.assertEqual(len(pending), 1)
        saved = asyncio.run(self.service.recover_creation(port, pending[0]))
        self.assertEqual(saved['discord_container_id'], 701)
        self.assertEqual(saved['status'], 'open')
        self.assertEqual(self.repository.pending_container_creations(1), [])

    def test_category_retry_preserves_original_return_category(self):
        class Port:
            current = 100
            async def category(self, ticket):
                return self.current
            async def move_category(self, ticket, target, *, expected):
                if self.current not in {target, expected}:
                    raise DiscordFailure('category conflict', partial=True)
                self.current = target
        panel = self.repository.save_panel(1, {'name': 'Waiting', 'mode': 'channel', 'category_id': 100,
            'team_id': self.team['id'], 'awaiting_category_id': 200})
        ticket, _ = self.service.reserve(1, panel['id'], 10, 'category-retry', set())
        ticket = self.repository.activate_ticket(ticket['id'], 700, 100)
        item = {'id': 40, 'created_at': 1000, 'action': 'awaiting_user'}
        port = Port()
        with patch.object(self.repository, 'set_awaiting_user', side_effect=RuntimeError('database failed')):
            with self.assertRaises(RuntimeError):
                asyncio.run(self.service.change_category(port, ticket, item))
        self.assertEqual(port.current, 200)
        asyncio.run(self.service.change_category(port, ticket, item))
        saved = self.repository.ticket(ticket['id'])
        self.assertEqual(saved['awaiting_return_category_id'], 100)
        asyncio.run(self.service.change_category(port, saved, item))
        asyncio.run(self.service.change_category(port, saved, {'id': 41, 'created_at': 1001, 'action': 'resume_awaiting'}))
        self.assertEqual(port.current, 100)
        self.assertEqual(self.repository.ticket(ticket['id'])['status'], 'open')

    def test_reply_success_database_failure_recovers_receipt_without_resending(self):
        class Port:
            sent = 0
            message = None
            async def send_reply(self, ticket, outbox_id, content, *, recover):
                if recover:
                    return self.message
                self.sent += 1
                self.message = {'id': 900, 'created_at': 1000}
                return self.message
        ticket, _ = self.service.reserve(1, self.panel['id'], 10, 'reply-recovery', set())
        ticket = self.repository.activate_ticket(ticket['id'], 700, 100)
        item = {'id': 30, 'created_at': 1000, 'action': 'reply', 'actor_id': 20,
                'payload': {'actor_name': 'Staff', 'content_encrypted': self.storage.encrypt_text('reply')}}
        port = Port()
        with patch.object(self.repository, 'record_message', side_effect=RuntimeError('database failed')):
            with self.assertRaises(RuntimeError):
                asyncio.run(self.service.deliver_message(port, ticket, item))
        asyncio.run(self.service.deliver_message(port, ticket, item))
        asyncio.run(self.service.deliver_message(port, ticket, item))
        self.assertEqual(port.sent, 1)
        self.assertEqual(len(self.repository.messages(ticket['id'])), 1)

    def test_known_unsent_reply_can_retry_as_a_new_send(self):
        class Port:
            calls = []
            async def send_reply(self, ticket, outbox_id, content, *, recover):
                self.calls.append(recover)
                if len(self.calls) == 1:
                    raise DiscordFailure('rate limited', retry=True)
                return {'id': 900, 'created_at': 1000}
        ticket, _ = self.service.reserve(1, self.panel['id'], 10, 'reply-rate-limit', set())
        ticket = self.repository.activate_ticket(ticket['id'], 700, 100)
        item = {'id': 30, 'created_at': 1000, 'action': 'reply', 'actor_id': 20,
                'payload': {'actor_name': 'Staff', 'content_encrypted': self.storage.encrypt_text('reply')}}
        port = Port()
        with self.assertRaises(DiscordFailure):
            asyncio.run(self.service.deliver_message(port, ticket, item))
        asyncio.run(self.service.deliver_message(port, ticket, item))
        self.assertEqual(port.calls, [False, False])

    def test_internal_note_retry_records_one_message(self):
        ticket, _ = self.service.reserve(1, self.panel['id'], 10, 'internal-note', set())
        ticket = self.repository.activate_ticket(ticket['id'], 700, 100)
        ticket = {**ticket, 'mode': 'private_thread'}
        item = {'id': 30, 'created_at': 1000, 'action': 'note', 'actor_id': 20,
                'payload': {'actor_name': 'Staff', 'content_encrypted': self.storage.encrypt_text('private note')}}
        asyncio.run(self.service.deliver_message(None, ticket, item))
        asyncio.run(self.service.deliver_message(None, ticket, item))
        rows = self.repository.messages(ticket['id'])
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]['discord_message_id'])

    def test_participant_database_failure_can_retry_without_false_completion(self):
        class Port:
            users = set()
            async def participant(self, ticket, user_id, *, add):
                self.users.add(user_id) if add else self.users.discard(user_id)
        ticket, _ = self.service.reserve(1, self.panel['id'], 10, 'participant-retry', set())
        ticket = self.repository.activate_ticket(ticket['id'], 700, 100)
        port = Port()
        with patch.object(self.repository, 'add_participant', side_effect=RuntimeError('database failed')):
            with self.assertRaises(RuntimeError):
                asyncio.run(self.service.change_participant(port, ticket, 20, 30, add=True))
        self.assertEqual(port.users, {20})
        asyncio.run(self.service.change_participant(port, ticket, 20, 30, add=True))
        self.assertEqual(port.users, {20})
        with self.assertRaisesRegex(ValueError, 'opener_removal_forbidden'):
            asyncio.run(self.service.change_participant(port, ticket, 10, 30, add=False))

    def test_close_resource_is_durable_and_old_revision_cannot_delete(self):
        from cogs.tickets import TicketsCog
        from types import SimpleNamespace
        ticket, _ = self.service.reserve(1, self.panel['id'], 10, 'durable-close', set())
        ticket = self.repository.activate_ticket(ticket['id'], 700, 100)
        self.repository.begin_close(ticket['id'], 20, 'resolved')
        closed = self.repository.close_ticket(ticket['id'], 20, 'resolved')
        claim = self.repository.outbox_jobs.claim('worker')
        self.assertEqual(claim.payload['action'], 'close_resource')
        cog = object.__new__(TicketsCog)
        cog.repository = self.repository
        cog.bot = SimpleNamespace(get_guild=lambda _: None)
        cog.discord = SimpleNamespace(set_closed=AsyncMock(side_effect=DiscordFailure('temporary failure', retry=True)))
        with patch.object(self.repository, 'transcript_for_ticket', return_value={'id': 1}):
            outcome = asyncio.run(cog._deliver_outbox_item(claim.payload))
        self.assertTrue(outcome.retry)
        self.assertEqual(self.repository.ticket(ticket['id'])['status'], 'closed')
        cog.discord.set_closed.reset_mock()
        stale = {**claim.payload, 'payload': {'revision': closed['revision'] - 1}}
        outcome = asyncio.run(cog._deliver_outbox_item(stale))
        self.assertEqual(outcome.error, 'revision_conflict')
        cog.discord.set_closed.assert_not_awaited()

    def test_claim_database_failure_and_failed_compensation_remain_recoverable(self):
        class Port:
            changed = False
            fail_restore = True
            async def claim_changes(self, *args):
                return [{'id': 500, 'kind': 'role', 'before': {'send_messages': False}, 'after': {'send_messages': True}}]
            async def permission(self, ticket, change, *, restore=False):
                if restore and self.fail_restore:
                    raise DiscordFailure('Forbidden')
                self.changed = not restore
        ticket, panel = self.service.reserve(1, self.panel['id'], 10, 'claim-recovery', set())
        ticket = self.repository.activate_ticket(ticket['id'], 700, 100)
        port = Port()
        with patch.object(self.repository, 'set_claim', side_effect=RuntimeError('database failed')):
            with self.assertRaises(RuntimeError):
                asyncio.run(self.service.change_claim(port, ticket, panel, 20, ticket['revision']))
        self.assertTrue(port.changed)
        operation = self.repository.pending_claim_changes(1)[0]
        with self.assertRaisesRegex(RuntimeError, 'claim_recovery_required'):
            asyncio.run(self.service.change_claim(port, ticket, panel, 30, ticket['revision']))
        port.fail_restore = False
        asyncio.run(self.service.recover_claim(port, operation))
        self.assertFalse(port.changed)
        self.assertEqual(self.repository.pending_claim_changes(1), [])
        saved = asyncio.run(self.service.change_claim(port, ticket, panel, 20, ticket['revision']))
        self.assertEqual(saved['claimed_by'], 20)
        self.assertEqual(self.repository.pending_claim_changes(1), [])

    def test_container_success_database_failure_records_and_recovers_orphan(self):
        class Port:
            async def create_container(self, *args):
                return ContainerRef(700, 100)
            async def recover_container(self, *args):
                return ContainerRef(700, 100)
        ticket, panel = self.service.reserve(1, self.panel['id'], 10, 'orphan-case', set())
        with patch.object(self.repository, 'activate_ticket', side_effect=RuntimeError('database unavailable')):
            with self.assertRaises(RuntimeError):
                asyncio.run(self.service.open_container(Port(), ticket, panel, 'ticket'))
        orphan = self.repository.pending_orphans(1)[0]
        self.assertEqual(orphan['container_id'], 700)
        self.assertEqual(self.repository.pending_orphans(2), [])
        saved = asyncio.run(self.service.recover_orphan(Port(), 1, orphan['id']))
        self.assertEqual((saved['status'], saved['discord_container_id']), ('open', 700))
        self.assertEqual(self.repository.pending_orphans(1), [])

    def test_partial_container_failure_keeps_resource_identity(self):
        class Port:
            async def create_container(self, *args):
                raise DiscordFailure('member permission lost', partial=True, resource_id=701)
        ticket, panel = self.service.reserve(1, self.panel['id'], 10, 'partial-container', set())
        with self.assertRaises(DiscordFailure):
            asyncio.run(self.service.open_container(Port(), ticket, panel, 'ticket'))
        self.assertEqual(self.repository.pending_orphans(1)[0]['container_id'], 701)

    def test_extracted_persistence_operations_preserve_scope_and_revision(self):
        repository = self.repository
        repository.set_blacklist(1, 10, 99, 'blocked')
        self.assertTrue(repository.is_blacklisted(1, 10))
        self.assertFalse(repository.is_blacklisted(2, 10))
        with self.assertRaises(TicketValidationError) as rejected:
            self.service.validate_open(1, self.panel['id'], 10, set())
        self.assertEqual(rejected.exception.code, 'blacklisted')
        repository.set_blacklist(1, 10, 99, None)
        repository.set_on_call(1, self.team['id'], 99, True)
        self.assertEqual(repository.on_call_members(1, self.team['id']), [99])
        self.assertEqual(repository.on_call_members(2, self.team['id']), [])
        repository.save_tag(1, 'Greeting', 'Hello', 99)
        self.assertEqual(repository.tag(1, 'GREETING'), {'content': 'Hello'})
        self.assertIsNone(repository.tag(2, 'Greeting'))
        ticket, _ = self.service.reserve(1, self.panel['id'], 10, 'persist', set())
        self.assertFalse(repository.transfer_panel(ticket['id'], self.panel['id']))
        ticket = repository.activate_ticket(ticket['id'], 200, 100)
        revision = ticket['revision']
        self.assertTrue(repository.transfer_panel(ticket['id'], self.panel['id']))
        repository.set_auto_close_excluded(ticket['id'], True)
        repository.mark_deleted(ticket['id'], 123)
        restarted = TicketRepository(repository.database_url)
        saved = restarted.ticket(ticket['id'])
        self.assertEqual(saved['revision'], revision + 3)
        self.assertTrue(saved['auto_close_excluded'])
        self.assertEqual(saved['deleted_at'], 123)

    def test_form_and_panel_limits(self):
        with self.assertRaises(ValueError):
            validate_form({"name": "Too many", "fields": [{"label": str(index)} for index in range(6)]})
        with self.assertRaises(ValueError):
            validate_panel({"name": "Thread", "mode": "private_thread", "team_id": self.team["id"]})

    def test_disabled_intake_rejects_new_tickets_but_preserves_existing_ticket(self):
        ticket, _ = self.service.reserve(1, self.panel['id'], 10, 'before-disable', set())
        self.repository.save_settings(1, {'enabled': False})
        with self.assertRaises(TicketValidationError) as rejected:
            self.service.reserve(1, self.panel['id'], 11, 'after-disable', set())
        self.assertEqual(rejected.exception.code, 'disabled')
        self.assertEqual(self.repository.ticket(ticket['id']), ticket)

    def test_reservation_is_idempotent_and_limit_is_guild_wide(self):
        first, _ = self.service.reserve(1, self.panel["id"], 10, "same", set())
        duplicate, _ = self.service.reserve(1, self.panel["id"], 10, "same", set())
        self.assertEqual(first["id"], duplicate["id"])
        with self.assertRaises(OverflowError):
            self.repository.reserve_ticket(1, self.panel["id"], 11, "other", {})
        staff = self.repository.reserve_ticket(1, self.panel["id"], 11, "staff", {}, staff_exempt=True)
        self.assertNotEqual(first["id"], staff["id"])

    def test_close_encrypts_answers_and_all_messages(self):
        form = self.repository.save_form(1, {"name": "Contact", "title": "Contact", "fields": [{"key": "reason", "label": "Reason"}]})
        panel = self.repository.save_panel(1, {"name": "Contact", "mode": "channel", "category_id": 100, "form_id": form["id"], "team_id": self.team["id"]})
        ticket, _ = self.service.reserve(1, panel["id"], 10, "close", set(), {"reason": "private"}, staff_exempt=True)
        ticket = self.repository.activate_ticket(ticket["id"], 200, 100)
        for index in range(501):
            self.service.record_message(ticket, index + 1, 10, "member", f"message {index}", [])
        closed, transcript = asyncio.run(self.service.close(ticket["id"], 99, "done"))
        payload = asyncio.run(self.storage.load(transcript["backend"], transcript["object_key"], transcript["content_hash"]))
        self.assertEqual("closed", closed["status"])
        self.assertEqual("private", payload["form_answers"]["reason"])
        self.assertEqual(501, len(payload["messages"]))

    def test_attachment_is_encrypted_and_integrity_checked(self):
        stored = asyncio.run(self.storage.save_attachment(1, 2, 3, b"attachment body"))
        self.assertEqual(b"attachment body", asyncio.run(self.storage.load_attachment(stored.backend, stored.object_key, stored.content_hash)))
        raw = (self.root / "blobs" / stored.object_key).read_bytes()
        self.assertNotIn(b"attachment body", raw)

    def test_auto_close_schedule_survives_repository_restart(self):
        self.repository.save_settings(1, {"enabled": True, "open_limit": 2, "default_auto_close": {"no_user_reply_minutes": 1}})
        ticket, _ = self.service.reserve(1, self.panel["id"], 10, "scheduled", set())
        ticket = self.repository.activate_ticket(ticket["id"], 300, 100)
        self.service.schedule_ticket(ticket)
        reopened = TicketRepository(prepare_database(self.root / "tickets.db", self.addCleanup))
        with reopened._connection() as connection:
            row = connection.execute('SELECT kind,status FROM ticket_schedules WHERE ticket_id=%s', (ticket["id"],)).fetchone()
        self.assertEqual(("no_user_reply", "pending"), tuple(row.values()))

    def test_support_hours_reports_next_open(self):
        panel = {"support_hours": {"timezone": "Asia/Tokyo", "weekdays": {"0": {"start": "09:00", "end": "17:00"}}}}
        opened, next_open = support_is_open(panel, datetime(2026, 8, 24, 8, 0, tzinfo=ZoneInfo("Asia/Tokyo")))
        self.assertFalse(opened)
        self.assertEqual(9, next_open.hour)
        overnight = {"support_hours": {"timezone": "Asia/Tokyo", "weekdays": {"0": {"start": "22:00", "end": "02:00"}}}}
        opened, _ = support_is_open(overnight, datetime(2026, 8, 25, 1, 0, tzinfo=ZoneInfo("Asia/Tokyo")))
        self.assertTrue(opened)

    def test_access_rules_require_allow_role_and_deny_wins(self):
        panel = self.repository.save_panel(1, {
            "name": "Restricted", "mode": "channel", "category_id": 100, "team_id": self.team["id"],
            "access_rules": [
                {"role_id": 10, "label": "Members", "allow": True},
                {"role_id": 20, "label": "Suspended", "allow": False},
            ],
        })
        with self.assertRaises(TicketValidationError) as missing:
            self.service.validate_open(1, panel["id"], 10, set())
        self.assertEqual("panel_forbidden", missing.exception.code)
        self.service.validate_open(1, panel["id"], 10, {10})
        with self.assertRaises(TicketValidationError) as denied:
            self.service.validate_open(1, panel["id"], 10, {10, 20})
        self.assertEqual("panel_forbidden", denied.exception.code)

    def test_panel_bundle_is_atomic_and_checks_both_revisions(self):
        bundle = self.repository.save_panel_bundle(1, {
            "panel": {"name": "Billing", "mode": "channel", "category_id": 100, "team_id": self.team["id"]},
            "deployment": {"name": "Support entry", "channel_id": 300, "title": "Need help?", "description": "Choose a ticket", "color": "#123456"},
            "welcome_embed": {"title": "Welcome", "description": "Ticket {ticket_number} for {user}"},
            "permissions": {"attach_files": False},
            "access_rules": [],
            "support_hours": {"timezone": "Asia/Tokyo", "weekdays": {}},
        })
        self.assertEqual("Welcome", bundle["panel"]["welcome_embed"]["title"])
        self.assertFalse(bundle["panel"]["creator_permissions"]["attach_files"])
        self.assertIn(bundle["panel"]["id"], bundle["deployment"]["panel_ids"])
        stale = json.loads(json.dumps(bundle))
        stale["panel"]["name"] = "Stale update"
        self.repository.save_panel(1, {**bundle["panel"], "name": "Current update"}, bundle["panel"]["id"], bundle["panel"]["revision"])
        with self.assertRaises(RuntimeError):
            self.repository.save_panel_bundle(1, stale, bundle["panel"]["id"])
        self.assertEqual("Current update", self.repository.panel(1, bundle["panel"]["id"])["name"])

    def test_panel_user_limit_cooldown_and_staff_exemption(self):
        self.repository.save_settings(1, {"enabled": True, "open_limit": 10})
        panel = self.repository.save_panel(1, {
            "name": "Limited", "mode": "channel", "category_id": 100, "team_id": self.team["id"],
            "per_user_open_limit": 1, "open_cooldown_seconds": 60,
        })
        first = self.repository.reserve_ticket(1, panel["id"], 10, "limit-1", {})
        first = self.repository.activate_ticket(first["id"], 500, 100)
        with self.assertRaisesRegex(OverflowError, "user_ticket_limit"):
            self.repository.reserve_ticket(1, panel["id"], 10, "limit-2", {})
        with self.repository._connection() as connection:
            connection.execute("UPDATE tickets_v2 SET status='closed',closed_at=%s WHERE id=%s", (int(datetime.now().timestamp()), first["id"]))
        with self.assertRaisesRegex(OverflowError, "ticket_cooldown"):
            self.repository.reserve_ticket(1, panel["id"], 10, "limit-3", {})
        staff = self.repository.reserve_ticket(1, panel["id"], 10, "limit-staff", {}, staff_exempt=True)
        self.assertEqual("creating", staff["status"])

    def test_awaiting_user_state_restores_original_category(self):
        ticket = self.repository.reserve_ticket(1, self.panel["id"], 10, "awaiting", {}, staff_exempt=True)
        ticket = self.repository.activate_ticket(ticket["id"], 600, 100)
        awaiting = self.repository.set_awaiting_user(ticket["id"], 100)
        self.assertEqual("awaiting_user", awaiting["status"])
        self.assertEqual(100, awaiting["awaiting_return_category_id"])
        resumed = self.repository.resume_awaiting_user(ticket["id"])
        self.assertEqual("open", resumed["status"])
        self.assertIsNone(resumed["awaiting_return_category_id"])


if __name__ == "__main__":
    unittest.main()
