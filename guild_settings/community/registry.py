"""Explicit community settings models."""
from ..defaults import SettingsModel
from .welcome import normalize as welcome
from .autorole import defaults as autorole
from .leveling import normalize as leveling
from .live_stats import normalize as live_stats
from .temporary_voice import normalize as temporary_voice
from insights.models import normalize as insights

MODELS = {
    'welcome': SettingsModel(welcome),
    'autorole': SettingsModel(defaults=autorole),
    'leveling': SettingsModel(leveling),
    'live_stats': SettingsModel(live_stats),
    'temporary_voice': SettingsModel(temporary_voice),
    'insights': SettingsModel(insights),
}
