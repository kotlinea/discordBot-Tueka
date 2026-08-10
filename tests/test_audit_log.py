import unittest
from pathlib import Path

from cogs.audit_log import AuditLogCog


class AuditLogCogTests(unittest.TestCase):
    def test_action_deduplication_expires_and_is_guild_scoped(self):
        cog = AuditLogCog.__new__(AuditLogCog)
        cog._recent_actions = {}
        self.assertTrue(cog._claim_action(1, "ban", 10))
        self.assertFalse(cog._claim_action(1, "ban", 10))
        self.assertTrue(cog._claim_action(2, "ban", 10))

    def test_log_text_is_bounded(self):
        self.assertLessEqual(len(AuditLogCog._short("x" * 2000)), 900)

    def test_member_category_requires_audit_log_permission_in_dashboard(self):
        template = Path("dashboard/templates/module_settings.html").read_text(encoding="utf-8")
        self.assertIn("toast.missing_permissions", template)
        self.assertIn('name="log_member"', template)
