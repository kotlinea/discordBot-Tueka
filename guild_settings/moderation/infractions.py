"""infractions persisted defaults."""
from .shared import normalize as normalize_exemptions

def normalize(settings):
    return normalize_exemptions(settings, {'point_thresholds': []})
