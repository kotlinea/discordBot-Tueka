"""Existing Bot-only roll command; no dashboard metadata or new guild toggle."""
from ..contracts import Binding, Feature

FEATURE = Feature('roll', 'engagement', dashboard=False, order=26, bindings=(Binding('roll_bot', 'bot', 'cogs.engagement.roll:setup', 0),))
