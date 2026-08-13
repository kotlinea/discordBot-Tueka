"""Typed validation boundary shared by the bot, storage and dashboard."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

try:
    import regex
except ImportError:  # Existing installations remain bootable until requirements are refreshed.
    import re as regex


TRIGGER_TYPES = {
    "keyword", "regex", "safe_browsing", "discord_invite", "domain",
    "message_rate", "duplicate", "mention_rate", "link_rate", "attachment_rate",
    "reaction_rate", "reaction_burst", "join_rate", "leave_rate", "new_account_ratio", "new_member_activity",
    "emoji_sticker_rate", "phishing_link", "caps", "media_only", "honeypot",
}
RATE_TRIGGERS = {"message_rate", "duplicate", "mention_rate", "link_rate", "attachment_rate", "reaction_rate", "reaction_burst", "join_rate", "leave_rate", "new_account_ratio", "emoji_sticker_rate"}
ACTION_TYPES = {"delete", "purge", "remove_reaction", "points", "notify", "dm", "timeout", "untimeout", "kick", "ban", "unban", "tempban", "softban", "lock", "unlock", "lockdown", "unlockdown", "log"}
TERMINAL_ACTIONS = {"kick", "ban", "tempban", "softban"}
RULE_FAMILIES = {"automod", "anti_spam", "anti_raid", "infraction"}
EVENT_TYPES = {"message_create", "message_edit", "reaction_add", "member_join", "member_remove", "infraction_change"}

TRIGGER_FAMILY = {
    **{item: "anti_spam" for item in ("message_rate", "duplicate", "mention_rate", "link_rate", "attachment_rate", "reaction_rate", "reaction_burst")},
    **{item: "anti_raid" for item in ("join_rate", "leave_rate", "new_account_ratio", "new_member_activity")},
}

TRIGGER_EVENT = {
    "reaction_rate": "reaction_add", "reaction_burst": "reaction_add",
    "join_rate": "member_join", "new_account_ratio": "member_join", "leave_rate": "member_remove",
}


def _ids(value: Any, limit: int = 100) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        try:
            parsed = int(item)
        except (TypeError, ValueError):
            raise ValueError("Invalid Discord resource ID")
        if parsed <= 0:
            raise ValueError("Invalid Discord resource ID")
        if parsed not in result:
            result.append(parsed)
    if len(result) > limit:
        raise ValueError("Too many Discord resource IDs")
    return result


def _integer(value: Any, default: int, low: int, high: int, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if not low <= parsed <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return parsed


def default_rule(trigger_type: str = "keyword") -> dict[str, Any]:
    if trigger_type not in TRIGGER_TYPES:
        trigger_type = "keyword"
    defaults: dict[str, dict[str, Any]] = {
        "keyword": {"keywords": [], "allow_list": [], "match": "wildcard"},
        "regex": {"patterns": []},
        "safe_browsing": {},
        "discord_invite": {},
        "domain": {"mode": "blacklist", "domains": []},
        "message_rate": {"limit": 6, "window_seconds": 10},
        "duplicate": {"limit": 3, "window_seconds": 10},
        "mention_rate": {"limit": 10, "window_seconds": 10},
        "link_rate": {"limit": 3, "window_seconds": 10},
        "attachment_rate": {"limit": 3, "window_seconds": 10},
        "reaction_rate": {"limit": 8, "window_seconds": 10},
        "reaction_burst": {"limit": 5, "window_seconds": 10},
        "join_rate": {"limit": 10, "window_seconds": 30},
        "leave_rate": {"limit": 10, "window_seconds": 30},
        "new_account_ratio": {"limit": 10, "window_seconds": 60, "account_age_days": 7, "percentage": 70},
        "new_member_activity": {"join_age_minutes": 10},
        "emoji_sticker_rate": {"limit": 20, "window_seconds": 10, "per_message_limit": 12},
        "phishing_link": {},
        "caps": {"percentage": 70, "minimum_letters": 6},
        "media_only": {"allow_links": True},
        "honeypot": {"channel_ids": []},
    }
    return {
        "name": "新しいModerationルール", "enabled": True, "mode": "monitor", "priority": 100,
        "family": TRIGGER_FAMILY.get(trigger_type, "automod"), "event_type": TRIGGER_EVENT.get(trigger_type, "message_create"),
        "stop_on_match": False, "trigger_type": trigger_type, "trigger_config": deepcopy(defaults[trigger_type]),
        "conditions": {}, "exemptions": {}, "actions": [{"type": "log"}],
    }


def validate_rule(raw: dict[str, Any]) -> dict[str, Any]:
    trigger = str(raw.get("trigger_type", ""))
    if trigger not in TRIGGER_TYPES:
        raise ValueError("Unknown AutoMod trigger")
    name = str(raw.get("name", "")).strip()
    if not name or len(name) > 100:
        raise ValueError("Rule name is required and must be at most 100 characters")
    mode = str(raw.get("mode", "enforce"))
    if mode not in {"monitor", "enforce"}:
        raise ValueError("Invalid AutoMod mode")
    family = str(raw.get("family") or TRIGGER_FAMILY.get(trigger, "automod"))
    event_type = str(raw.get("event_type") or TRIGGER_EVENT.get(trigger, "message_create"))
    if family not in RULE_FAMILIES or event_type not in EVENT_TYPES:
        raise ValueError("Invalid Moderation rule family or event")
    if trigger in TRIGGER_FAMILY and family != TRIGGER_FAMILY[trigger]:
        raise ValueError("Trigger is not available in this Moderation family")
    if trigger in TRIGGER_EVENT and event_type != TRIGGER_EVENT[trigger]:
        raise ValueError("Trigger does not support this event type")
    config = dict(raw.get("trigger_config") or {})
    if trigger == "keyword":
        config["keywords"] = [str(item).strip()[:60] for item in config.get("keywords", []) if str(item).strip()][:1000]
        config["allow_list"] = [str(item).strip()[:60] for item in config.get("allow_list", []) if str(item).strip()][:100]
        config["match"] = config.get("match") if config.get("match") in {"wildcard", "contains"} else "wildcard"
        if not config["keywords"]:
            raise ValueError("Keyword rules require at least one keyword")
    elif trigger == "regex":
        patterns = [str(item).strip() for item in config.get("patterns", []) if str(item).strip()]
        if not patterns or len(patterns) > 20 or any(len(item) > 260 for item in patterns):
            raise ValueError("Regex rules require 1 to 20 patterns of at most 260 characters")
        for pattern in patterns:
            try:
                regex.compile(pattern, regex.IGNORECASE)
            except regex.error as exc:
                raise ValueError(f"Invalid regular expression: {exc}") from exc
            if regex.__name__ == "re" and __import__("re").search(r"\([^)]*[+*][^)]*\)[+*{]", pattern):
                raise ValueError("Nested quantifiers require the timeout-capable regex dependency")
        config = {"patterns": patterns}
    elif trigger == "domain":
        mode_value = str(config.get("mode", "blacklist"))
        if mode_value not in {"blacklist", "block_all_except"}:
            raise ValueError("Invalid domain rule mode")
        domains = [str(item).strip().lower().rstrip(".")[:253] for item in config.get("domains", []) if str(item).strip()]
        if not domains or len(domains) > 500:
            raise ValueError("Domain rules require 1 to 500 domains")
        config = {"mode": mode_value, "domains": list(dict.fromkeys(domains))}
    elif trigger in RATE_TRIGGERS:
        config = {"limit": _integer(config.get("limit"), 3, 1 if trigger != "duplicate" else 2, 100, "limit"),
                  "window_seconds": _integer(config.get("window_seconds"), 10, 1, 300, "window_seconds")}
        if trigger == "new_account_ratio":
            config.update({"account_age_days": _integer(raw.get("trigger_config", {}).get("account_age_days"), 7, 1, 3650, "account_age_days"),
                           "percentage": _integer(raw.get("trigger_config", {}).get("percentage"), 70, 1, 100, "percentage")})
        elif trigger == "emoji_sticker_rate":
            config["per_message_limit"] = _integer(raw.get("trigger_config", {}).get("per_message_limit"), 12, 1, 100, "per_message_limit")
        elif trigger == "duplicate":
            config["similarity_percent"] = _integer(raw.get("trigger_config", {}).get("similarity_percent"), 100, 70, 100, "similarity_percent")
    elif trigger == "new_member_activity":
        config = {"join_age_minutes": _integer(config.get("join_age_minutes"), 10, 1, 10080, "join_age_minutes")}
    elif trigger == "caps":
        config = {"percentage": _integer(config.get("percentage"), 70, 10, 100, "percentage"),
                  "minimum_letters": _integer(config.get("minimum_letters"), 6, 1, 100, "minimum_letters")}
    elif trigger == "media_only":
        config = {"allow_links": bool(config.get("allow_links", True))}
    elif trigger == "honeypot":
        config = {"channel_ids": _ids(config.get("channel_ids"), 20)}
        if not config["channel_ids"]:
            raise ValueError("Honeypot rules require at least one channel")
    else:
        config = {}

    conditions_raw, exemptions_raw = dict(raw.get("conditions") or {}), dict(raw.get("exemptions") or {})
    conditions = {
        "channel_ids": _ids(conditions_raw.get("channel_ids")),
        "category_ids": _ids(conditions_raw.get("category_ids")),
        "required_role_ids": _ids(conditions_raw.get("required_role_ids")),
        "excluded_role_ids": _ids(conditions_raw.get("excluded_role_ids")),
        "minimum_account_age_days": _integer(conditions_raw.get("minimum_account_age_days", 0), 0, 0, 3650, "minimum_account_age_days"),
        "minimum_join_age_days": _integer(conditions_raw.get("minimum_join_age_days", 0), 0, 0, 3650, "minimum_join_age_days"),
        "user_ids": _ids(conditions_raw.get("user_ids")),
        "bot_ids": _ids(conditions_raw.get("bot_ids")),
        "webhook_ids": _ids(conditions_raw.get("webhook_ids")),
        "actor_kinds": [item for item in dict.fromkeys(str(item) for item in conditions_raw.get("actor_kinds", [])) if item in {"human", "bot", "webhook"}],
    }
    exemptions = {"channel_ids": _ids(exemptions_raw.get("channel_ids")), "category_ids": _ids(exemptions_raw.get("category_ids")), "role_ids": _ids(exemptions_raw.get("role_ids")), "user_ids": _ids(exemptions_raw.get("user_ids")), "bot_ids": _ids(exemptions_raw.get("bot_ids")), "webhook_ids": _ids(exemptions_raw.get("webhook_ids"))}
    actions: list[dict[str, Any]] = []
    for raw_action in raw.get("actions", []):
        action = dict(raw_action)
        action_type = str(action.get("type", ""))
        if action_type not in ACTION_TYPES:
            raise ValueError("Unknown AutoMod action")
        normalized: dict[str, Any] = {"type": action_type}
        if action_type == "points":
            normalized["points"] = _integer(action.get("points"), 1, 1, 1000, "points")
            normalized["expires_days"] = _integer(action.get("expires_days", 30), 30, 0, 3650, "expires_days")
        elif action_type == "timeout":
            normalized["duration_minutes"] = _integer(action.get("duration_minutes"), 10, 1, 40320, "duration_minutes")
        elif action_type == "tempban":
            normalized["duration_minutes"] = _integer(action.get("duration_minutes"), 60, 1, 525600, "duration_minutes")
        elif action_type == "purge":
            normalized["count"] = _integer(action.get("count"), 10, 1, 100, "count")
        elif action_type == "lockdown":
            normalized["duration_minutes"] = _integer(action.get("duration_minutes"), 30, 1, 1440, "duration_minutes")
            normalized["channel_ids"] = _ids(action.get("channel_ids"), 100)
            normalized["category_ids"] = _ids(action.get("category_ids"), 100)
        elif action_type in {"notify", "dm"}:
            normalized["message"] = str(action.get("message", "ルール違反を検知しました。"))[:500]
            if action_type == "notify" and action.get("channel_id"):
                normalized["channel_id"] = _ids([action["channel_id"]], 1)[0]
        actions.append(normalized)
    if mode == "enforce" and not actions:
        raise ValueError("Enforced rules require at least one action")
    if sum(action["type"] in TERMINAL_ACTIONS for action in actions) > 1:
        raise ValueError("Only one kick, ban or temporary ban action is allowed per rule")
    return {
        "name": name, "enabled": bool(raw.get("enabled", True)), "mode": mode, "family": family, "event_type": event_type,
        "priority": _integer(raw.get("priority"), 100, 0, 10000, "priority"),
        "stop_on_match": bool(raw.get("stop_on_match", False)), "trigger_type": trigger,
        "trigger_config": config, "conditions": conditions, "exemptions": exemptions, "actions": actions,
    }
