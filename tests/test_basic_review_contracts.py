import math
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from cogs.engagement.calculate import _safe_calculate
from cogs.engagement.roll import RollCog


class CalculationBoundaries(unittest.TestCase):
    def test_bounded_arithmetic_and_unsupported_input(self):
        for expression, expected in (('0', 0), ('1', 1), ('2**12', 4096), ('-(3 + 4) % 5', 3), ('1/2', 0.5)):
            self.assertEqual(_safe_calculate(expression), expected)
        for expression in ('2**13', '1/0', 'True', '__import__("os")', '1e309', '9' * 201, '(-1)**0.5'):
            with self.subTest(expression=expression), self.assertRaises((ValueError, ZeroDivisionError, SyntaxError)):
                _safe_calculate(expression)


class RollBoundaries(unittest.IsolatedAsyncioTestCase):
    async def test_finite_positive_range_and_invalid_edges(self):
        for sides in (1.0, 6.0, 1000000.0, 0.5, 0.0, -1.0, 1000001.0, math.nan, math.inf):
            response = SimpleNamespace(send_message=AsyncMock())
            await RollCog.roll.callback(RollCog(), SimpleNamespace(response=response), sides)
            args, kwargs = response.send_message.call_args
            self.assertLessEqual(len(args[0]), 2000)
            self.assertEqual(bool(kwargs.get('ephemeral')), not (math.isfinite(sides) and 0 < sides <= 1000000))

