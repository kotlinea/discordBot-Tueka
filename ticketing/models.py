"""Typed validation and defaults for the Ticket V2 domain."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


TICKET_MODES = {"channel", "private_thread"}
CLAIM_MODES = {"claim_only_reply", "shared_reply", "claim_only_view"}
FORM_STYLES = {"short", "paragraph"}
PANEL_NAME_VARIABLES = {"number", "username", "user_id", "panel"}
WELCOME_VARIABLES = {"ticket_number", "user", "username", "user_id", "panel", "team"}
BUTTON_STYLES = {"primary", "secondary", "success", "danger"}
CREATOR_PERMISSION_DEFAULTS = {
    "add_reactions": True,
    "send_tts_messages": False,
    "embed_links": True,
    "attach_files": True,
    "use_external_emojis": True,
    "use_external_stickers": True,
    "send_voice_messages": True,
}


def default_embed(description: str = "") -> dict[str, Any]:
    return {
        "color": "#5865F2", "title": "", "title_url": "", "description": description,
        "author": {"enabled": False, "name": "", "icon_url": "", "url": ""},
        "image_url": "", "thumbnail_url": "",
        "footer": {"enabled": False, "text": "", "icon_url": "", "timestamp": False},
        "fields": [],
    }


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
        "transcript_channel_id": None,
        "awaiting_category_id": None,
        "exit_form_id": None,
        "required_role_ids": [],
        "mention_role_ids": [],
        "mention_user_ids": [],
        "remove_mentions": False,
        "open_cooldown_seconds": 0,
        "per_user_open_limit": 1,
        "ticket_name_template": "ticket-{number}-{username}",
        "allow_user_close": True,
        "anonymous_dashboard_replies": False,
        "feedback_enabled": False,
        "show_claim_button": True,
        "show_close_button": True,
        "show_close_reason_button": True,
        "button": {"style": "primary", "label": "チケットを作成", "emoji": ""},
        "claim_mode": "claim_only_reply",
        "support_hours": {"timezone": "Asia/Tokyo", "weekdays": {}},
        "creator_permissions": dict(CREATOR_PERMISSION_DEFAULTS),
        "access_rules": [],
        "welcome_embed": default_embed("サポート担当者が順番に対応します。お問い合わせ内容を送信してください。"),
        "auto_close": None,
        "color": "#5865F2",
        "enabled": True,
    }


def default_deployment() -> dict[str, Any]:
    return {
        "panel_message_id": None, "revision": None, "name": "", "channel_id": None,
        "content": "", "title": "サポートチケット", "description": "下のボタンからお問い合わせください。",
        "color": "#5865F2", "image_url": "", "thumbnail_url": "", "position": None,
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


def _url(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if text and urlparse(text).scheme not in {"http", "https"}:
        raise ValueError(field)
    if len(text) > 2048:
        raise ValueError(field)
    return text


def _validate_template(value: Any, *, maximum: int, variables: set[str], field: str) -> str:
    text = str(value or "")
    if len(text) > maximum or set(re.findall(r"\{([a-z_]+)\}", text)) - variables:
        raise ValueError(field)
    return text


def validate_embed(value: Any, *, description: str = "") -> dict[str, Any]:
    raw = {**default_embed(description), **dict(value or {})}
    color = str(raw.get("color") or "#5865F2").upper()
    if not re.fullmatch(r"#[0-9A-F]{6}", color):
        raise ValueError("embed_color")
    title = _validate_template(raw.get("title"), maximum=256, variables=WELCOME_VARIABLES, field="embed_title")
    body = _validate_template(raw.get("description"), maximum=4096, variables=WELCOME_VARIABLES, field="embed_description")
    author_raw = dict(raw.get("author") or {})
    footer_raw = dict(raw.get("footer") or {})
    author = {
        "enabled": bool(author_raw.get("enabled")),
        "name": _validate_template(author_raw.get("name"), maximum=256, variables=WELCOME_VARIABLES, field="embed_author"),
        "icon_url": _url(author_raw.get("icon_url"), "embed_author_icon"),
        "url": _url(author_raw.get("url"), "embed_author_url"),
    }
    footer = {
        "enabled": bool(footer_raw.get("enabled")),
        "text": _validate_template(footer_raw.get("text"), maximum=2048, variables=WELCOME_VARIABLES, field="embed_footer"),
        "icon_url": _url(footer_raw.get("icon_url"), "embed_footer_icon"),
        "timestamp": bool(footer_raw.get("timestamp")),
    }
    fields = raw.get("fields") or []
    if not isinstance(fields, list) or len(fields) > 25:
        raise ValueError("embed_fields")
    normalized_fields = []
    for item in fields:
        if not isinstance(item, dict):
            raise ValueError("embed_fields")
        name = _validate_template(item.get("name"), maximum=256, variables=WELCOME_VARIABLES, field="embed_field_name")
        field_value = _validate_template(item.get("value"), maximum=1024, variables=WELCOME_VARIABLES, field="embed_field_value")
        if not name or not field_value:
            raise ValueError("embed_fields")
        normalized_fields.append({"name": name, "value": field_value, "inline": bool(item.get("inline"))})
    if len(title) + len(body) + len(author["name"]) + len(footer["text"]) + sum(len(item["name"]) + len(item["value"]) for item in normalized_fields) > 6000:
        raise ValueError("embed_total")
    return {
        "color": color, "title": title, "title_url": _url(raw.get("title_url"), "embed_title_url"),
        "description": body, "author": author, "image_url": _url(raw.get("image_url"), "embed_image_url"),
        "thumbnail_url": _url(raw.get("thumbnail_url"), "embed_thumbnail_url"), "footer": footer,
        "fields": normalized_fields,
    }


def validate_deployment(value: Any) -> dict[str, Any]:
    raw = {**default_deployment(), **dict(value or {})}
    result = {
        "panel_message_id": int(raw["panel_message_id"]) if raw.get("panel_message_id") not in (None, "") else None,
        "revision": int(raw["revision"]) if raw.get("revision") not in (None, "") else None,
        "name": str(raw.get("name") or "").strip(),
        "channel_id": int(raw["channel_id"]) if raw.get("channel_id") not in (None, "") else None,
        "content": str(raw.get("content") or ""), "title": str(raw.get("title") or "").strip(),
        "description": str(raw.get("description") or ""), "color": str(raw.get("color") or "#5865F2").upper(),
        "image_url": _url(raw.get("image_url"), "panel_image_url"),
        "thumbnail_url": _url(raw.get("thumbnail_url"), "panel_thumbnail_url"),
        "position": int(raw["position"]) if raw.get("position") not in (None, "") else None,
    }
    if result["channel_id"] is not None:
        if not result["name"] or len(result["name"]) > 80 or not result["title"]:
            raise ValueError("panel_message")
    if len(result["content"]) > 2000 or len(result["title"]) > 256 or len(result["description"]) > 4096:
        raise ValueError("panel_message")
    if not re.fullmatch(r"#[0-9A-F]{6}", result["color"]):
        raise ValueError("panel_message_color")
    return result


def validate_panel(value: dict[str, Any]) -> dict[str, Any]:
    incoming = dict(value or {})
    result = {**default_panel(), **incoming}
    result["name"] = str(result["name"]).strip()
    result["description"] = str(result["description"]).strip()
    if not result["name"] or len(result["name"]) > 80 or len(result["description"]) > 4000:
        raise ValueError("panel_name")
    if result["mode"] not in TICKET_MODES or result["claim_mode"] not in CLAIM_MODES:
        raise ValueError("panel_mode")
    for key in ("form_id", "team_id", "category_id", "thread_parent_channel_id", "staff_notification_channel_id", "transcript_channel_id", "awaiting_category_id", "exit_form_id"):
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
    for key in ("allow_user_close", "anonymous_dashboard_replies", "feedback_enabled", "show_claim_button", "show_close_button", "show_close_reason_button", "remove_mentions", "enabled"):
        result[key] = bool(result[key])
    result["open_cooldown_seconds"] = max(0, min(int(result.get("open_cooldown_seconds", 0)), 604800))
    result["per_user_open_limit"] = max(1, min(int(result.get("per_user_open_limit", 1)), 25))
    result["support_hours"] = _validate_support_hours(result.get("support_hours"))
    permissions = dict(result.get("creator_permissions") or {})
    result["creator_permissions"] = {key: bool(permissions.get(key, default)) for key, default in CREATOR_PERMISSION_DEFAULTS.items()}
    button = dict(result.get("button") or {})
    button_style = str(button.get("style") or "primary")
    button_label = str(button.get("label") or result["name"]).strip()
    button_emoji = str(button.get("emoji") or "").strip()
    if button_style not in BUTTON_STYLES or not button_label or len(button_label) > 80 or len(button_emoji) > 100:
        raise ValueError("panel_button")
    result["button"] = {"style": button_style, "label": button_label, "emoji": button_emoji}
    rules = result.get("access_rules") or []
    if not isinstance(rules, list) or len(rules) > 100:
        raise ValueError("access_rules")
    normalized_rules = []
    seen_roles: set[int] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("access_rules")
        role_id = int(rule.get("role_id", 0))
        label = str(rule.get("label") or "").strip()
        if role_id <= 0 or role_id in seen_roles or len(label) > 80:
            raise ValueError("access_rules")
        seen_roles.add(role_id)
        normalized_rules.append({"role_id": role_id, "label": label, "allow": bool(rule.get("allow", True))})
    result["access_rules"] = normalized_rules
    result["welcome_embed"] = validate_embed(result.get("welcome_embed") if "welcome_embed" in incoming else {"description": result["description"], "color": result.get("color")})
    if result.get("auto_close") is not None:
        result["auto_close"] = validate_settings({"default_auto_close": result["auto_close"]})["default_auto_close"]
    color = str(result.get("color") or "#5865F2").upper()
    if not re.fullmatch(r"#[0-9A-F]{6}", color):
        raise ValueError("color")
    result["color"] = color
    result["revision"] = max(1, int(result.get("revision", 1)))
    return result


def validate_panel_bundle(value: dict[str, Any]) -> dict[str, Any]:
    raw = dict(value or {})
    panel = dict(raw.get("panel") or {})
    for source, target in (("welcome_embed", "welcome_embed"), ("permissions", "creator_permissions"),
                           ("access_rules", "access_rules"), ("support_hours", "support_hours")):
        if source in raw:
            panel[target] = raw[source]
    return {"panel": validate_panel(panel), "deployment": validate_deployment(raw.get("deployment"))}


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
