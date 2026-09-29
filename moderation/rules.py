"""Rule family selection and unsaved defaults, independent of HTTP and storage."""
from typing import Any

from .models import default_rule, validate_rule


FAMILY_TRIGGERS = {'automod': ('keyword', 'regex', 'safe_browsing', 'phishing_link', 'discord_invite', 'domain', 'caps', 'emoji_sticker_rate', 'media_only', 'honeypot'), 'anti_spam': ('message_rate', 'duplicate', 'mention_rate', 'link_rate', 'attachment_rate', 'reaction_rate', 'reaction_burst'), 'anti_raid': ('join_rate', 'leave_rate', 'new_account_ratio', 'new_member_activity')}


def rule_template(family: str, trigger: str) -> dict[str, Any]:
    if trigger not in FAMILY_TRIGGERS.get(family, ()):
        raise ValueError('trigger_type')
    return {**default_rule(trigger), 'enabled': False}


def validate_activation(rule: dict[str, Any]) -> None:
    """Check stored configuration before enabling; never rewrite its contents."""
    if rule['trigger_type'] not in FAMILY_TRIGGERS.get(rule['family'], ()):
        raise ValueError('trigger_type')
    validate_rule(rule)
