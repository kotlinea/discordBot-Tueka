from ..defaults import SettingsModel
from .suggestions import normalize
from .scheduled_messages import normalize as scheduled_normalize

MODELS = {'suggestions': SettingsModel(normalize), 'scheduled_messages': SettingsModel(scheduled_normalize)}
