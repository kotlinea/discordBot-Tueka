import unittest

from cogs.moderation.action_support.direct_commands import MAX_TIMEOUT, SafetyCog


class SafetyValidationTests(unittest.TestCase):
    def test_legacy_message_handlers_are_not_registered(self):
        from cogs.moderation.moderation import ModerationCog
        for cog in (SafetyCog, ModerationCog):
            self.assertFalse(hasattr(cog, '_legacy_on_message_disabled'))
            self.assertNotIn('on_message', {name for name, _ in cog.__cog_listeners__})

    def test_timeout_limit_matches_discord_limit(self):
        self.assertEqual(MAX_TIMEOUT, 28 * 24 * 60)
