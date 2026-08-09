import unittest

from cogs.general import HelpView, MAX_ROLL_SIDES, _build_embed, _safe_calculate


class GeneralCommandTests(unittest.TestCase):
    def test_calculator_accepts_basic_expression(self):
        self.assertEqual(_safe_calculate("2 * (3 + 4)"), 14)

    def test_calculator_rejects_expensive_power(self):
        with self.assertRaises(ValueError):
            _safe_calculate("2 ** 13")

    def test_calculator_rejects_unsupported_syntax(self):
        with self.assertRaises(ValueError):
            _safe_calculate("__import__('os')")

    def test_help_view_disables_first_previous_button(self):
        view = HelpView(1, [("基本", [])])
        self.assertTrue(view.previous.disabled)
        self.assertTrue(view.next.disabled)

    def test_roll_limit_is_practical(self):
        self.assertEqual(MAX_ROLL_SIDES, 1_000_000)

    def test_embed_builder_supports_embed_fields(self):
        embed = _build_embed("Title", "Description", "#5865F2", None, "Author", None, None, "Footer", None, None, None, '[{"name":"Field","value":"Value","inline":true}]', True)
        self.assertEqual(embed.title, "Title")
        self.assertEqual(len(embed.fields), 1)

    def test_embed_builder_rejects_too_many_fields(self):
        fields = "[" + ",".join('{"name":"n","value":"v"}' for _ in range(26)) + "]"
        with self.assertRaises(ValueError):
            _build_embed(None, None, None, None, None, None, None, None, None, None, None, fields, False)
