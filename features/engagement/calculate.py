"""Existing Bot-only calculate command; no dashboard metadata or new guild toggle."""
from ..contracts import Binding, Feature

FEATURE = Feature('calculate', 'engagement', dashboard=False, order=25)

