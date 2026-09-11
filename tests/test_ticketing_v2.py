import asyncio
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet

from ticketing import TicketRepository, TicketService, TicketValidationError, TranscriptStorage, validate_form, validate_panel
from ticketing.models import support_is_open


class TicketV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repository = TicketRepository(self.root / "tickets.db")
        self.storage = TranscriptStorage(self.root / "blobs", Fernet.generate_key().decode("ascii"))
        self.service = TicketService(self.repository, self.storage)
        self.repository.save_settings(1, {"enabled": True, "open_limit": 1})
        self.team = self.repository.save_team(1, {"name": "Staff", "role_ids": [500]})
        self.panel = self.repository.save_panel(1, {"name": "Support", "mode": "channel", "category_id": 100, "team_id": self.team["id"]})

    def tearDown(self):
        self.temp.cleanup()

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
        reopened = TicketRepository(self.root / "tickets.db")
        with reopened._connection() as connection:
            row = connection.execute("SELECT kind,status FROM ticket_schedules WHERE ticket_id=?", (ticket["id"],)).fetchone()
        self.assertEqual(("no_user_reply", "pending"), tuple(row))

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
            connection.execute("UPDATE tickets_v2 SET status='closed',closed_at=? WHERE id=?", (int(datetime.now().timestamp()), first["id"]))
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
