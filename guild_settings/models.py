"""Pure normalization of persisted guild module settings."""
from typing import Any
from template_defaults import TEMPLATE_DEFAULTS


def template_module_settings(module_id: str, settings: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "live_stats": {"stats_channel_id": None, "stats_template": TEMPLATE_DEFAULTS["stats_template"]},
        "temporary_voice": {"temp_voice_trigger_id": None, "temp_voice_category_id": None, "temp_voice_name": TEMPLATE_DEFAULTS["temp_voice_name"]},
    }[module_id]
    defaults.update(settings)
    field = "stats_template" if module_id == "live_stats" else "temp_voice_name"
    if not str(defaults.get(field) or "").strip():
        defaults[field] = TEMPLATE_DEFAULTS[field]
    return defaults

def audit_log_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Apply explicit category defaults."""
    defaults: dict[str, Any] = {
        "management_channel_id": None,
        "log_message": False,
        "log_voice": False,
        "log_channel": False,
        "log_member": False,
        "log_role": False,
        "log_server": False,
    }
    defaults.update(settings)
    return defaults

def leveling_settings(settings: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "text_notification_channel_id": None,
        "text_role_rewards": [],
        "voice_enabled": False,
        "voice_notification_channel_id": None,
        "voice_role_rewards": [],
        "voice_xp_per_minute": 5,
        "voice_allow_solo": False,
        "voice_allow_muted": False,
    }
    defaults.update(settings)
    return defaults

def automod_settings(settings: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "log_channel_id": None,
        "immune_role_ids": [],
        "immune_user_ids": [],
        "immune_channel_ids": [],
        "evidence_excluded_channel_ids": [],
        "evidence_retention_days": 30,
        "point_thresholds": [],
        "rules_revision": 0,
    }
    defaults.update(settings)
    for key in ("immune_role_ids", "immune_user_ids", "immune_channel_ids", "evidence_excluded_channel_ids"):
        defaults[key] = list(dict.fromkeys(int(value) for value in defaults.get(key, []) if str(value).isdigit()))[:100]
    defaults["evidence_retention_days"] = max(1, min(int(defaults.get("evidence_retention_days", 30)), 365))
    return defaults

def moderation_settings(settings: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "default_log_channel_id": None, "immune_role_ids": [], "immune_user_ids": [],
        "immune_channel_ids": [], "evidence_excluded_channel_ids": [], "evidence_retention_days": 30,
        "exclude_bots": True, "exclude_webhooks": True, "rules_revision": 0,
        "escalation_enabled": False, "escalation_threshold": 3, "escalation_action": "timeout",
        "escalation_timeout_minutes": 60, "dm_notify": False,
    }
    defaults.update(settings)
    for key in ("immune_role_ids", "immune_user_ids", "immune_channel_ids", "evidence_excluded_channel_ids"):
        defaults[key] = list(dict.fromkeys(int(value) for value in defaults.get(key, []) if str(value).isdigit()))[:100]
    defaults["evidence_retention_days"] = max(1, min(int(defaults.get("evidence_retention_days", 30)), 365))
    return defaults

def moderation_submodule_settings(module_id: str, settings: dict[str, Any]) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "log_channel_id": None, "immune_role_ids": [], "immune_user_ids": [], "immune_channel_ids": [],
    }
    if module_id == "infractions":
        defaults["point_thresholds"] = []
    elif module_id == "anti_raid":
        defaults.update({"default_lockdown_minutes": 30, "notify_channel_id": None})
    elif module_id == "moderation_logs":
        defaults.update({f"log_{name}": True for name in ("message_delete", "message_edit", "warning", "timeout", "kick", "ban", "unban", "join", "leave", "automod", "anti_spam", "anti_raid", "admin")})
    defaults.update(settings)
    for key in ("immune_role_ids", "immune_user_ids", "immune_channel_ids"):
        defaults[key] = list(dict.fromkeys(int(value) for value in defaults.get(key, []) if str(value).isdigit()))[:100]
    return defaults

