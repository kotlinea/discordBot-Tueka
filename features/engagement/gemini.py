"""Existing Bot-only gemini command; no dashboard metadata or new guild toggle."""
from ..contracts import Binding, Feature

FEATURE = Feature('gemini', 'engagement', dashboard=False, order=27, bindings=(Binding('gemini_bot', 'bot', 'cogs.engagement.gemini:setup', 1),))

