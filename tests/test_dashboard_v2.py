from dashboard.repository import DashboardRepository
from db_support import prepare_database
import tempfile
import unittest
from pathlib import Path

from dashboard.api_v1 import _normalize_resource_ids, _serialize_resource_ids, _serialize_rule_resource_ids
from storage import GuildStorage


class DashboardV2StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.storage = GuildStorage(prepare_database(Path(self.temp.name) / "dashboard-v2.db"))
        self.dashboard_repository = DashboardRepository(self.storage.database_path)

    def tearDown(self):
        self.temp.cleanup()

    def test_preferences_are_account_scoped_and_revision_checked(self):
        self.assertEqual(self.dashboard_repository.dashboard_preferences(10)["appearance"], "precision")
        saved = self.dashboard_repository.set_dashboard_preferences(
            10, locale="en", appearance="atmosphere", color_scheme="dark",
            navigation_collapsed=True, expected_revision=0,
        )
        self.assertEqual(saved["revision"], 1)
        self.assertTrue(saved["navigation_collapsed"])
        self.assertEqual(self.dashboard_repository.dashboard_preferences(11)["locale"], "ja")
        with self.assertRaisesRegex(RuntimeError, "revision_conflict"):
            self.dashboard_repository.set_dashboard_preferences(
                10, locale="ja", appearance="community", color_scheme="light",
                navigation_collapsed=False, expected_revision=0,
            )

    def test_module_explicit_save_increments_revision(self):
        initial = self.storage.get_module(1, "welcome")
        saved = self.storage.set_module(1, "welcome", enabled=True, settings=initial["settings"], expected_revision=0)
        self.assertEqual(saved["revision"], 1)
        with self.assertRaisesRegex(RuntimeError, "revision_conflict"):
            self.storage.set_module(1, "welcome", enabled=False, expected_revision=0)

    def test_discord_snowflakes_round_trip_as_json_safe_strings(self):
        trigger_id = "123456789012345678"
        role_ids = ["123456789012345679", "123456789012345680"]
        normalized = _normalize_resource_ids({"temp_voice_trigger_id": trigger_id, "reaction_role_ids": role_ids})
        self.assertEqual(normalized["temp_voice_trigger_id"], int(trigger_id))
        self.assertEqual(normalized["reaction_role_ids"], [int(item) for item in role_ids])
        self.assertEqual(_serialize_resource_ids(normalized), {"temp_voice_trigger_id": trigger_id, "reaction_role_ids": role_ids})
        rule = _serialize_rule_resource_ids({"conditions": {"channel_ids": [int(trigger_id)]}, "exemptions": {"role_ids": [int(role_ids[0])]}, "trigger_config": {}, "actions": [{"type": "notify", "channel_id": int(trigger_id)}]})
        self.assertEqual(rule["conditions"]["channel_ids"], [trigger_id])
        self.assertEqual(rule["exemptions"]["role_ids"], [role_ids[0]])
        self.assertEqual(rule["actions"][0]["channel_id"], trigger_id)


if __name__ == "__main__":
    unittest.main()
