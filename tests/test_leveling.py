import unittest

from cogs.leveling import calculate_level, required_xp


class LevelingMathTests(unittest.TestCase):
    def test_level_formula_remains_compatible(self):
        self.assertEqual(required_xp(0), 100)
        self.assertEqual(calculate_level(100), (1, 0))
        self.assertEqual(calculate_level(255), (2, 0))
