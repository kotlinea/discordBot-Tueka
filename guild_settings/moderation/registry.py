"""Explicit moderation settings models."""
from ..defaults import SettingsModel
from .moderation import normalize as moderation
from .automod import normalize as automod
from .audit_log import normalize as audit_log
from .anti_spam import normalize as anti_spam
from .anti_raid import normalize as anti_raid
from .infractions import normalize as infractions
from .moderation_actions import normalize as moderation_actions
from .moderation_logs import normalize as moderation_logs
from .appeals import normalize as appeals

MODELS = {
    'appeals': SettingsModel(appeals),
    'moderation': SettingsModel(moderation),
    'automod': SettingsModel(automod),
    'audit_log': SettingsModel(audit_log),
    'anti_spam': SettingsModel(anti_spam),
    'anti_raid': SettingsModel(anti_raid),
    'infractions': SettingsModel(infractions),
    'moderation_actions': SettingsModel(moderation_actions),
    'moderation_logs': SettingsModel(moderation_logs),
}
