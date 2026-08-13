import tempfile
import unittest
from pathlib import Path

from storage import GuildStorage


class DashboardV2StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.storage = GuildStorage(Path(self.temp.name) / "dashboard-v2.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_preferences_are_account_scoped_and_revision_checked(self):
        self.assertEqual(self.storage.dashboard_preferences(10)["appearance"], "precision")
        saved = self.storage.set_dashboard_preferences(
            10, locale="en", appearance="atmosphere", color_scheme="dark",
            navigation_collapsed=True, expected_revision=0,
        )
        self.assertEqual(saved["revision"], 1)
        self.assertTrue(saved["navigation_collapsed"])
        self.assertEqual(self.storage.dashboard_preferences(11)["locale"], "ja")
        with self.assertRaisesRegex(RuntimeError, "revision_conflict"):
            self.storage.set_dashboard_preferences(
                10, locale="ja", appearance="community", color_scheme="light",
                navigation_collapsed=False, expected_revision=0,
            )

    def test_module_explicit_save_increments_revision(self):
        initial = self.storage.get_module(1, "welcome")
        saved = self.storage.set_module(1, "welcome", enabled=True, settings=initial["settings"], expected_revision=0)
        self.assertEqual(saved["revision"], 1)
        with self.assertRaisesRegex(RuntimeError, "revision_conflict"):
            self.storage.set_module(1, "welcome", enabled=False, expected_revision=0)


if __name__ == "__main__":
    unittest.main()

