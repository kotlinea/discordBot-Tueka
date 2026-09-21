"""Pure temporary_voice settings normalization."""
from template_defaults import TEMPLATE_DEFAULTS

def normalize(settings):
    defaults = {"temp_voice_trigger_id": None, "temp_voice_category_id": None, "temp_voice_name": TEMPLATE_DEFAULTS["temp_voice_name"]}
    defaults.update(settings)
    if not str(defaults.get('temp_voice_name') or '').strip():
        defaults['temp_voice_name'] = TEMPLATE_DEFAULTS['temp_voice_name']
    return defaults
