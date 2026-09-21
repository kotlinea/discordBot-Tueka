"""anti_raid persisted defaults."""
from .shared import normalize as normalize_exemptions

def normalize(settings):
    return normalize_exemptions(settings, {'default_lockdown_minutes': 30, 'notify_channel_id': None})
