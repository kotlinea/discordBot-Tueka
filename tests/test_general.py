import unittest

from cogs.general import HelpView, MAX_ROLL_SIDES, _safe_calculate


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
