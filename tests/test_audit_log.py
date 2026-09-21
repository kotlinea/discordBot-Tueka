import unittest
from pathlib import Path

from cogs.moderation.audit_log import AuditLogCog


class AuditLogCogTests(unittest.TestCase):
    def test_action_deduplication_expires_and_is_guild_scoped(self):
        cog = AuditLogCog.__new__(AuditLogCog)
        cog._recent_actions = {}
        self.assertTrue(cog._claim_action(1, "ban", 10))
        self.assertFalse(cog._claim_action(1, "ban", 10))
        self.assertTrue(cog._claim_action(2, "ban", 10))

    def test_log_text_is_bounded(self):
        self.assertLessEqual(len(AuditLogCog._short("x" * 2000)), 900)

    def test_moderation_log_categories_are_selected_per_event(self):
        self.assertEqual(AuditLogCog._event_key("📝 メッセージ編集"), "message_edit")
        self.assertEqual(AuditLogCog._event_key("🗑️ メッセージ削除"), "message_delete")
        self.assertEqual(AuditLogCog._event_key("⛔ メンバーBAN"), "ban")
        self.assertEqual(AuditLogCog._event_key("✅ BAN解除"), "unban")
        self.assertIsNone(AuditLogCog._event_key("📨 メッセージ投稿"))
