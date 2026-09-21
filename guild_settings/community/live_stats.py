"""Pure live_stats settings normalization."""
from template_defaults import TEMPLATE_DEFAULTS

def normalize(settings):
    defaults = {"stats_channel_id": None, "stats_template": TEMPLATE_DEFAULTS["stats_template"]}
    defaults.update(settings)
    if not str(defaults.get('stats_template') or '').strip():
        defaults['stats_template'] = TEMPLATE_DEFAULTS['stats_template']
    return defaults
