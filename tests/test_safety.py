import unittest

from cogs.safety import MAX_TIMEOUT, SafetyCog


class SafetyValidationTests(unittest.TestCase):
    def test_regex_rejects_invalid_or_risky_patterns(self):
        self.assertIsNotNone(SafetyCog._safe_regex(r"discord\\.gg/\\w+"))
        self.assertIsNone(SafetyCog._safe_regex("(a+)+$"))
        self.assertIsNone(SafetyCog._safe_regex("["))

    def test_timeout_limit_matches_discord_limit(self):
        self.assertEqual(MAX_TIMEOUT, 28 * 24 * 60)
