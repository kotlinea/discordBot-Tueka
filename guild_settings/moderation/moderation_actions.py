"""moderation_actions persisted defaults."""
from .shared import normalize as normalize_exemptions

def normalize(settings):
    return normalize_exemptions(settings, {})
