"""Existing Bot-only echo command; no dashboard metadata or new guild toggle."""
from ..contracts import Binding, Feature

FEATURE = Feature('echo', 'engagement', dashboard=False, order=24)

