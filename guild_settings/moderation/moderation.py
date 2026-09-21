"""Pure moderation settings normalization."""
from typing import Any

def normalize(settings: dict[str, Any]) -> dict[str, Any]:
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
