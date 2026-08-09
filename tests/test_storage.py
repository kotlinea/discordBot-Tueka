import json
import tempfile
import unittest
from pathlib import Path

from storage import GuildStorage


class GuildStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.storage = GuildStorage(self.root / "bot.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_settings_and_user_stats_are_shared(self):
        self.storage.update_settings(1, management_channel_id=10, welcome_channel_id=11, default_role_id=12)
        self.storage.add_xp(1, 99, 25)
        self.assertEqual(self.storage.get_settings(1)["welcome_channel_id"], 11)
        self.assertEqual(self.storage.get_user(1, 99), {"xp": 25, "warn": 0})

    def test_json_migration_is_one_time_and_preserves_data(self):
        data_dir = self.root / "data"
        data_dir.mkdir()
        (data_dir / "123.json").write_text(json.dumps({"management_channel_id": 7, "users": {"4": {"xp": 42, "warn": 2}}}), encoding="utf-8")
        self.assertEqual(self.storage.migrate_json(data_dir), 1)
        self.assertEqual(self.storage.get_settings(123)["management_channel_id"], 7)
        self.assertEqual(self.storage.get_user(123, 4), {"xp": 42, "warn": 2})
        self.assertEqual(self.storage.migrate_json(data_dir), 0)

    def test_dashboard_session_is_expiring_and_revocable(self):
        self.storage.create_dashboard_session("session", "access-token", 60)
        self.assertEqual(self.storage.dashboard_session_token("session"), "access-token")
        self.storage.delete_dashboard_session("session")
        self.assertIsNone(self.storage.dashboard_session_token("session"))

    def test_oauth_state_is_single_use(self):
        self.storage.create_oauth_state("state")
        self.assertTrue(self.storage.consume_oauth_state("state"))
        self.assertFalse(self.storage.consume_oauth_state("state"))

    def test_module_toggle_preserves_its_settings(self):
        self.storage.set_module(1, "welcome", enabled=True, settings={"welcome_channel_id": 10, "default_role_id": 20})
        self.storage.set_module(1, "welcome", enabled=False)
        module = self.storage.get_module(1, "welcome")
        self.assertFalse(module["enabled"])
        self.assertEqual(module["settings"]["welcome_channel_id"], 10)

    def test_new_modules_start_disabled(self):
        self.assertFalse(self.storage.get_module(1, "moderation")["enabled"])

    def test_legacy_role_setting_maps_to_autorole(self):
        self.storage.update_settings(1, default_role_id=20)
        self.assertEqual(self.storage.get_module(1, "autorole")["settings"]["default_role_id"], 20)

    def test_moderation_case_keeps_audit_details(self):
        self.storage.add_case(1, 2, "timeout", "reason", moderator_id=3, expires_at=100, dm_sent=True)
        case = self.storage.recent_cases(1, 2)[0]
        self.assertEqual(case["action"], "timeout")
        self.assertEqual(case["moderator_id"], 3)
        self.assertEqual(case["expires_at"], 100)
        self.assertEqual(case["dm_sent"], 1)

    def test_reaction_role_panel_rejects_unsafe_sizes_and_round_trips(self):
        with self.assertRaises(ValueError):
            self.storage.save_reaction_role_panel(10, 1, [])
        with self.assertRaises(ValueError):
            self.storage.save_reaction_role_panel(10, 1, list(range(26)))
        self.storage.save_reaction_role_panel(10, 1, [2, 3])
        self.assertEqual(self.storage.reaction_role_panel(10), {"guild_id": 1, "role_ids": [2, 3]})

    def test_community_automation_state_is_guild_scoped(self):
        self.storage.add_temporary_voice_channel(10, 1, 2)
        self.assertEqual(self.storage.temporary_voice_channel(10), {"guild_id": 1, "owner_id": 2})
        self.storage.remove_temporary_voice_channel(10)
        self.assertIsNone(self.storage.temporary_voice_channel(10))
        self.storage.create_ticket(20, 1, 2)
        self.storage.close_ticket(20, 3, [{"content": "help"}])
        ticket = self.storage.ticket(20)
        self.assertEqual(ticket["status"], "closed")
        self.assertEqual(ticket["closed_by"], 3)
        self.assertEqual(json.loads(ticket["transcript_json"]), [{"content": "help"}])

    def test_poll_votes_are_atomic_per_member_and_can_close(self):
        self.storage.create_poll(30, 1, 4, 2, "Question", ["A", "B"], None, None)
        self.assertEqual(self.storage.cast_poll_vote(30, 99, 0), [1, 0])
        self.assertEqual(self.storage.cast_poll_vote(30, 99, 1), [0, 1])

    def test_trust_score_has_reasons_and_manual_release(self):
        self.storage.set_module(1, "trust_score", enabled=True)
        self.storage.add_case(1, 2, "warn", "test warning")
        trust = self.storage.trust_score(1, 2)
        self.assertEqual(trust["score"], 90)
        self.assertEqual(trust["events"][0]["reason"], "test warning")
        self.storage.clear_trust_events(1, 2)
        self.assertEqual(self.storage.trust_score(1, 2)["score"], 100)

    def test_disabled_trust_module_does_not_collect_events(self):
        self.storage.add_case(1, 2, "warn", "not collected")
        self.assertEqual(self.storage.trust_score(1, 2)["score"], 100)
