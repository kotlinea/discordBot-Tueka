"""moderation_logs persisted defaults."""
from .shared import normalize as normalize_exemptions

def normalize(settings):
    return normalize_exemptions(settings, {f'log_{name}': True for name in ('message_delete', 'message_edit', 'warning', 'timeout', 'kick', 'ban', 'unban', 'join', 'leave', 'automod', 'anti_spam', 'anti_raid', 'admin')})
