from ..defaults import SettingsModel
from .suggestions import normalize
from .scheduled_messages import normalize as scheduled_normalize
from .advanced_polls import normalize as polls_normalize

MODELS = {'suggestions': SettingsModel(normalize), 'scheduled_messages': SettingsModel(scheduled_normalize), 'advanced_polls': SettingsModel(polls_normalize)}
