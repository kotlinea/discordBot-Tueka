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
