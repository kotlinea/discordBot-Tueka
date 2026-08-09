"""Single source of truth for dashboard feature modules."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Feature:
    id: str
    category: str
    title_key: str
    description_key: str
    icon: str
    fields: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()
    required_bot_permissions: tuple[str, ...] = ()


FEATURES = (
    Feature("welcome", "community", "feature.welcome", "feature.welcome.description", "users", ("welcome_channel_id",), ("welcome_channel_id",), ("send_messages",)),
    Feature("autorole", "community", "field.default_role", "settings.enable.description", "shield", ("default_role_id",), ("default_role_id",), ("manage_roles",)),
    Feature("leveling", "community", "feature.leveling", "feature.leveling.description", "chart", ()),
    Feature("audit_log", "moderation", "feature.audit_log", "feature.audit_log.description", "clipboard", ("management_channel_id",), ("management_channel_id",), ("send_messages",)),
    Feature("moderation", "moderation", "feature.moderation", "feature.moderation.description", "shield", ("escalation_enabled", "escalation_threshold", "escalation_action", "escalation_timeout_minutes", "dm_notify"), (), ("moderate_members", "kick_members", "ban_members")),
    Feature("chat_filter", "moderation", "feature.chat_filter", "feature.chat_filter.description", "shield", ("filter_keywords", "filter_regex", "filter_action", "safe_browsing_enabled"), (), ("manage_messages",)),
    Feature("anti_spam", "moderation", "feature.anti_spam", "feature.anti_spam.description", "shield", ("spam_window_seconds", "spam_message_limit", "spam_mention_limit", "spam_duplicate_limit", "spam_action", "spam_timeout_minutes"), (), ("manage_messages",)),
    Feature("reaction_roles", "community", "feature.reaction_roles", "feature.reaction_roles.description", "users", ("reaction_role_channel_id", "reaction_role_ids", "reaction_role_title", "reaction_role_description"), ("reaction_role_channel_id", "reaction_role_ids"), ("manage_roles", "send_messages")),
    Feature("live_stats", "community", "feature.live_stats", "feature.live_stats.description", "chart", ("stats_channel_id", "stats_template"), ("stats_channel_id",), ("manage_channels",)),
    Feature("temporary_voice", "community", "feature.temporary_voice", "feature.temporary_voice.description", "users", ("temp_voice_trigger_id", "temp_voice_category_id", "temp_voice_name"), ("temp_voice_trigger_id",), ("manage_channels", "move_members")),
    Feature("tickets", "community", "feature.tickets", "feature.tickets.description", "clipboard", ("ticket_panel_channel_id", "ticket_category_id", "ticket_staff_role_id", "ticket_log_channel_id", "ticket_panel_title", "ticket_panel_description"), ("ticket_panel_channel_id", "ticket_category_id", "ticket_staff_role_id"), ("manage_channels", "send_messages")),
    Feature("advanced_polls", "community", "feature.advanced_polls", "feature.advanced_polls.description", "chart", ()),
    Feature("minigames", "community", "feature.minigames", "feature.minigames.description", "users", ()),
    Feature("trust_score", "moderation", "feature.trust_score", "feature.trust_score.description", "shield", ("trust_retention_days", "trust_flag_threshold")),
)
FEATURE_BY_ID = {feature.id: feature for feature in FEATURES}


def get_feature(feature_id: str) -> Feature:
    try:
        return FEATURE_BY_ID[feature_id]
    except KeyError as exc:
        raise ValueError("Unknown feature") from exc
