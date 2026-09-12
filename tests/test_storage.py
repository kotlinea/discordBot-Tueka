import json
import tempfile
import unittest
from pathlib import Path

from storage import GuildStorage
from social_models import default_templates
from template_defaults import TEMPLATE_DEFAULTS


class GuildStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.storage = GuildStorage(self.root / "bot.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_settings_and_user_stats_are_shared(self):
        self.storage.set_module(1, "welcome", enabled=False, settings={"welcome_channel_id": 11})
        self.storage.add_xp(1, 99, 25)
        self.assertEqual(self.storage.get_module(1, "welcome")["settings"]["welcome_channel_id"], 11)
        self.assertEqual(self.storage.get_user(1, 99), {"xp": 25})

    def test_voice_xp_is_independent_from_text_xp_and_ranked(self):
        self.storage.add_xp(1, 99, 25)
        self.storage.add_voice_xp(1, 99, 10)
        self.storage.add_voice_xp(1, 100, 20)
        self.assertEqual(self.storage.get_user(1, 99)["xp"], 25)
        self.assertEqual(self.storage.get_voice_user(1, 99)["xp"], 10)
        self.assertEqual(self.storage.voice_leaderboard(1), [{"user_id": 100, "xp": 20}, {"user_id": 99, "xp": 10}])

    def test_leveling_uses_explicit_notification_channel(self):
        self.storage.set_module(1, "leveling", enabled=False, settings={"text_notification_channel_id": 77})
        leveling = self.storage.get_module(1, "leveling")
        self.assertFalse(leveling["enabled"])
        self.assertEqual(leveling["settings"]["text_notification_channel_id"], 77)
        self.assertFalse(leveling["settings"]["voice_enabled"])

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

    def test_template_fields_have_defaults_and_blank_values_are_normalized(self):
        welcome = self.storage.get_module(1, "welcome")["settings"]
        self.assertEqual(welcome["welcome_content"], TEMPLATE_DEFAULTS["welcome_content"])
        self.assertEqual(welcome["leave_content"], TEMPLATE_DEFAULTS["leave_content"])
        self.assertEqual(self.storage.get_module(1, "live_stats")["settings"]["stats_template"], TEMPLATE_DEFAULTS["stats_template"])
        self.assertEqual(self.storage.get_module(1, "temporary_voice")["settings"]["temp_voice_name"], TEMPLATE_DEFAULTS["temp_voice_name"])

        self.storage.set_module(1, "welcome", enabled=False, settings={"welcome_content": " ", "leave_content": ""})
        self.storage.set_module(1, "live_stats", enabled=False, settings={"stats_template": ""})
        self.storage.set_module(1, "temporary_voice", enabled=False, settings={"temp_voice_name": ""})
        self.assertEqual(self.storage.get_module(1, "welcome")["settings"]["welcome_content"], TEMPLATE_DEFAULTS["welcome_content"])
        self.assertEqual(self.storage.get_module(1, "live_stats")["settings"]["stats_template"], TEMPLATE_DEFAULTS["stats_template"])
        self.assertEqual(self.storage.get_module(1, "temporary_voice")["settings"]["temp_voice_name"], TEMPLATE_DEFAULTS["temp_voice_name"])

    def test_autorole_uses_own_settings(self):
        self.storage.set_module(1, "autorole", enabled=False, settings={"default_role_id": 20})
        self.assertEqual(self.storage.get_module(1, "autorole")["settings"]["default_role_id"], 20)

    def test_welcome_channel_alone_does_not_enable_messages(self):
        self.storage.set_module(1, "welcome", enabled=False, settings={"welcome_channel_id": 20})
        welcome = self.storage.get_module(1, "welcome")
        self.assertFalse(welcome["enabled"])
        self.assertEqual(welcome["settings"]["welcome_channel_id"], 20)
        self.assertFalse(welcome["settings"]["welcome_enabled"])
        self.assertFalse(welcome["settings"]["leave_enabled"])

    def test_audit_log_requires_explicit_category_selection(self):
        self.storage.set_module(1, "audit_log", enabled=True, settings={"management_channel_id": 20})
        audit_log = self.storage.get_module(1, "audit_log")
        self.assertFalse(audit_log["settings"]["log_message"])
        self.assertFalse(audit_log["settings"]["log_voice"])
        self.assertFalse(audit_log["settings"]["log_member"])
        self.assertFalse(self.storage.get_module(2, "audit_log")["settings"]["log_message"])

    def test_social_subscription_limit_and_event_deduplication(self):
        templates = default_templates("youtube", ["video"])
        for index in range(10):
            self.storage.save_social_subscription_v2(1, "youtube", f"UC{index}", 100, ["video"], {}, templates)
        with self.assertRaises(OverflowError):
            self.storage.save_social_subscription_v2(1, "youtube", "UC-over", 100, ["video"], {}, templates)
        self.assertTrue(self.storage.enqueue_social_event_v2("youtube", "video:1", "UC0", "video", {"type": "video"}))
        self.assertFalse(self.storage.enqueue_social_event_v2("youtube", "video:1", "UC0", "video", {"type": "video"}))
        self.assertEqual(len(self.storage.matching_social_subscriptions("youtube", "UC0", "video")), 1)

    def test_social_oauth_state_is_single_use_and_bound_to_provider(self):
        self.storage.create_social_oauth_state("social-state", 123, "tiktok")
        self.assertIsNone(self.storage.consume_social_oauth_state("social-state", "instagram"))
        self.storage.create_social_oauth_state("social-state", 123, "tiktok")
        self.assertEqual(self.storage.consume_social_oauth_state("social-state", "tiktok"), 123)
        self.assertIsNone(self.storage.consume_social_oauth_state("social-state", "tiktok"))

    def test_moderation_case_keeps_audit_details(self):
        self.storage.add_case(1, 2, "timeout", "reason", moderator_id=3, expires_at=100, dm_sent=True)
        case = self.storage.recent_cases(1, 2)[0]
        self.assertEqual(case["action"], "timeout")
        self.assertEqual(case["moderator_id"], 3)
        self.assertEqual(case["expires_at"], 100)
        self.assertEqual(case["dm_sent"], 1)


    def test_temporary_voice_state_is_guild_scoped(self):
        self.storage.add_temporary_voice_channel(10, 1, 2)
        self.assertEqual(self.storage.temporary_voice_channel(10), {"guild_id": 1, "owner_id": 2})
        self.storage.remove_temporary_voice_channel(10)
        self.assertIsNone(self.storage.temporary_voice_channel(10))

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
