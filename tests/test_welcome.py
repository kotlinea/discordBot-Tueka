import unittest
from types import SimpleNamespace

from cogs.welcome import WelcomeCog


class WelcomeTemplateTests(unittest.TestCase):
    def setUp(self):
        self.member = SimpleNamespace(
            mention="<@42>",
            name="plain*name*",
            display_name="display_name",
            guild=SimpleNamespace(name="Test * Server", member_count=12, members=[]),
        )

    def test_all_supported_variables_are_replaced(self):
        result = WelcomeCog.render_content("{user}|{username}|{displayname}|{server}|{membercount}", self.member)
        self.assertEqual(result, "<@42>|plain\\*name\\*|display\\_name|Test \\* Server|12")

    def test_unknown_variables_remain_literal(self):
        result = WelcomeCog.render_content("Hello {unknown} {123} {user}", self.member)
        self.assertEqual(result, "Hello \\{unknown\\} \\{123\\} <@42>")
