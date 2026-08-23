"""Typed validation and defaults for the Ticket V2 domain."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


TICKET_MODES = {"channel", "private_thread"}
CLAIM_MODES = {"claim_only_reply", "shared_reply", "claim_only_view"}
FORM_STYLES = {"short", "paragraph"}
PANEL_NAME_VARIABLES = {"number", "username", "user_id", "panel"}


def default_settings() -> dict[str, Any]:
    return {
        "enabled": False,
        "open_limit": 1,
        "language": "ja",
        "log_channel_id": None,
        "transcript_channel_id": None,
        "transcript_retention_days": 365,
        "close_dm": True,
        "default_auto_close": {
            "on_member_leave": False,
            "no_user_reply_minutes": 0,
            "inactivity_minutes": 0,
        },
        "revision": 1,
    }


def default_panel() -> dict[str, Any]:
    return {
        "name": "サポート",
        "description": "サポートが必要な場合はこちらからお問い合わせください。",
        "mode": "channel",
        "form_id": None,
        "team_id": None,
        "category_id": None,
        "thread_parent_channel_id": None,
        "staff_notification_channel_id": None,
        "required_role_ids": [],
        "mention_role_ids": [],
        "mention_user_ids": [],
        "ticket_name_template": "ticket-{number}-{username}",
        "allow_user_close": True,
        "anonymous_dashboard_replies": False,
        "feedback_enabled": False,
        "show_claim_button": True,
        "show_close_button": True,
        "show_close_reason_button": True,
        "claim_mode": "claim_only_reply",
        "support_hours": {"timezone": "Asia/Tokyo", "weekdays": {}},
        "creator_permissions": {"send_messages": True, "attach_files": True, "add_reactions": True, "send_tts_messages": False},
        "auto_close": None,
        "color": "#5865F2",
        "enabled": True,
    }


def _ids(value: Any, *, maximum: int = 100) -> list[int]:
    if value in (None, ""):
        return []
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError("resource_ids")
    result = [int(item) for item in value]
    if any(item <= 0 for item in result) or len(set(result)) != len(result):
        raise ValueError("resource_ids")
    return result


def validate_settings(value: dict[str, Any]) -> dict[str, Any]:
    result = {**default_settings(), **dict(value or {})}
    result["enabled"] = bool(result["enabled"])
    result["open_limit"] = max(1, min(int(result["open_limit"]), 25))
    if result["language"] not in {"ja", "en"}:
        raise ValueError("language")
    for key in ("log_channel_id", "transcript_channel_id"):
        result[key] = int(result[key]) if result.get(key) not in (None, "") else None
    result["transcript_retention_days"] = max(1, min(int(result["transcript_retention_days"]), 3650))
    result["close_dm"] = bool(result["close_dm"])
    auto = {**default_settings()["default_auto_close"], **dict(result.get("default_auto_close") or {})}
    auto["on_member_leave"] = bool(auto["on_member_leave"])
    auto["no_user_reply_minutes"] = max(0, min(int(auto["no_user_reply_minutes"]), 525600))
    auto["inactivity_minutes"] = max(0, min(int(auto["inactivity_minutes"]), 525600))
    result["default_auto_close"] = auto
    result["revision"] = max(1, int(result.get("revision", 1)))
    return result


def validate_form(value: dict[str, Any]) -> dict[str, Any]:
    name = str(value.get("name", "")).strip()
    title = str(value.get("title", name)).strip()
    if not name or len(name) > 80 or not title or len(title) > 45:
        raise ValueError("form_name")
    fields = value.get("fields") or []
    if not isinstance(fields, list) or len(fields) > 5:
        raise ValueError("form_fields")
    normalized = []
    seen: set[str] = set()
    for index, item in enumerate(fields):
        if not isinstance(item, dict):
            raise ValueError("form_field")
        key = str(item.get("key") or f"field_{index + 1}").strip().lower()
        label = str(item.get("label", "")).strip()
        placeholder = str(item.get("placeholder", "")).strip()
        style = str(item.get("style", "short"))
        minimum, maximum = int(item.get("min_length", 0)), int(item.get("max_length", 4000 if style == "paragraph" else 400))
        if not re.fullmatch(r"[a-z0-9_-]{1,40}", key) or key in seen or not label or len(label) > 45 or len(placeholder) > 100:
            raise ValueError("form_field")
        if style not in FORM_STYLES or minimum < 0 or maximum < max(1, minimum) or maximum > 4000:
            raise ValueError("form_field_limits")
        seen.add(key)
        normalized.append({"key": key, "label": label, "placeholder": placeholder, "style": style,
                           "required": bool(item.get("required", True)), "min_length": minimum, "max_length": maximum})
    return {"name": name, "title": title, "fields": normalized, "revision": max(1, int(value.get("revision", 1)))}


def _validate_support_hours(value: Any) -> dict[str, Any]:
    raw = dict(value or {})
    timezone = str(raw.get("timezone") or "Asia/Tokyo")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("support_timezone") from exc
    weekdays = raw.get("weekdays") or {}
    if not isinstance(weekdays, dict):
        raise ValueError("support_hours")
    normalized: dict[str, dict[str, str]] = {}
    for day, hours in weekdays.items():
        if str(day) not in {str(index) for index in range(7)} or not isinstance(hours, dict):
            raise ValueError("support_hours")
        start, end = str(hours.get("start", "")), str(hours.get("end", ""))
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", start) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", end):
            raise ValueError("support_hours")
        normalized[str(day)] = {"start": start, "end": end}
    return {"timezone": timezone, "weekdays": normalized}


def validate_panel(value: dict[str, Any]) -> dict[str, Any]:
    result = {**default_panel(), **dict(value or {})}
    result["name"] = str(result["name"]).strip()
    result["description"] = str(result["description"]).strip()
    if not result["name"] or len(result["name"]) > 80 or len(result["description"]) > 4000:
        raise ValueError("panel_name")
    if result["mode"] not in TICKET_MODES or result["claim_mode"] not in CLAIM_MODES:
        raise ValueError("panel_mode")
    for key in ("form_id", "team_id", "category_id", "thread_parent_channel_id", "staff_notification_channel_id"):
        result[key] = int(result[key]) if result.get(key) not in (None, "") else None
    if not result["team_id"]:
        raise ValueError("team_id")
    if result["mode"] == "channel" and not result["category_id"]:
        raise ValueError("category_id")
    if result["mode"] == "private_thread" and (not result["thread_parent_channel_id"] or not result["staff_notification_channel_id"]):
        raise ValueError("thread_channels")
    for key in ("required_role_ids", "mention_role_ids", "mention_user_ids"):
        result[key] = _ids(result.get(key))
    template = str(result.get("ticket_name_template") or "ticket-{number}-{username}")
    unknown = set(re.findall(r"\{([a-z_]+)\}", template)) - PANEL_NAME_VARIABLES
    if unknown or len(template) > 100:
        raise ValueError("ticket_name_template")
    result["ticket_name_template"] = template
    for key in ("allow_user_close", "anonymous_dashboard_replies", "feedback_enabled", "show_claim_button", "show_close_button", "show_close_reason_button", "enabled"):
        result[key] = bool(result[key])
    result["support_hours"] = _validate_support_hours(result.get("support_hours"))
    permissions = dict(result.get("creator_permissions") or {})
    result["creator_permissions"] = {key: bool(permissions.get(key, default)) for key, default in default_panel()["creator_permissions"].items()}
    if result.get("auto_close") is not None:
        result["auto_close"] = validate_settings({"default_auto_close": result["auto_close"]})["default_auto_close"]
    color = str(result.get("color") or "#5865F2").upper()
    if not re.fullmatch(r"#[0-9A-F]{6}", color):
        raise ValueError("color")
    result["color"] = color
    result["revision"] = max(1, int(result.get("revision", 1)))
    return result


def support_is_open(panel: dict[str, Any], now: datetime | None = None) -> tuple[bool, datetime | None]:
    support = panel.get("support_hours") or {}
    weekdays = support.get("weekdays") or {}
    if not weekdays:
        return True, None
    zone = ZoneInfo(str(support.get("timezone") or "Asia/Tokyo"))
    current = (now or datetime.now(zone)).astimezone(zone)
    next_open: datetime | None = None
    # Start with yesterday so an overnight window (for example 22:00–02:00)
    # remains open after midnight on the following calendar day.
    for offset in range(-1, 8):
        date = current.date() + timedelta(days=offset)
        hours = weekdays.get(str(date.weekday()))
        if not hours:
            continue
        start_hour, start_minute = map(int, hours["start"].split(":"))
        end_hour, end_minute = map(int, hours["end"].split(":"))
        start = datetime(date.year, date.month, date.day, start_hour, start_minute, tzinfo=zone)
        end = datetime(date.year, date.month, date.day, end_hour, end_minute, tzinfo=zone)
        if end <= start:
            end += timedelta(days=1)
        if start <= current < end:
            return True, None
        if start > current and (next_open is None or start < next_open):
            next_open = start
    return False, next_open
