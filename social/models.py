"""Validation and normalized payload helpers for social notifications."""
from __future__ import annotations

import re
import unicodedata
from typing import Any
from urllib.parse import unquote, urlparse


PROVIDERS = ("youtube", "twitch", "tiktok", "x", "instagram")
PROVIDER_EVENTS = {
    "youtube": ("video", "live_start", "live_end"),
    "twitch": ("live_start", "live_end"),
    "tiktok": ("post", "live_start", "live_end"),
    "x": ("post",),
    "instagram": ("post", "reel"),
}
TEMPLATE_VARIABLES = ("account", "handle", "title", "text", "url", "platform", "event", "published_at", "thumbnail", "avatar", "viewer_count")
VARIABLE_PATTERN = re.compile(r"\{(" + "|".join(TEMPLATE_VARIABLES) + r")\}")
UNKNOWN_VARIABLE_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
YOUTUBE_CHANNEL_ID = re.compile(r"UC[A-Za-z0-9_-]{22}")
YOUTUBE_HANDLE_SEPARATORS = frozenset("_-.·")


def _youtube_identifier(value: str) -> str:
    candidate = unicodedata.normalize("NFC", unquote(value).strip()).lstrip("@")
    if YOUTUBE_CHANNEL_ID.fullmatch(candidate):
        return candidate
    if not candidate or len(candidate) > 30 or candidate[0] in YOUTUBE_HANDLE_SEPARATORS or candidate[-1] in YOUTUBE_HANDLE_SEPARATORS:
        raise ValueError("YouTube handle is invalid")
    for character in candidate:
        if character in YOUTUBE_HANDLE_SEPARATORS:
            continue
        if unicodedata.category(character)[0] not in {"L", "M", "N"}:
            raise ValueError("YouTube handle is invalid")
    directions = {unicodedata.bidirectional(character) for character in candidate}
    if directions & {"L"} and directions & {"R", "AL"}:
        raise ValueError("YouTube handle cannot mix left-to-right and right-to-left scripts")
    return candidate.casefold()


def _normalize_youtube_account(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("YouTube channel is required")
    if not candidate.startswith(("http://", "https://")):
        return _youtube_identifier(candidate)

    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower().rstrip(".")
    if host != "youtube.com" and not host.endswith(".youtube.com"):
        raise ValueError("YouTube channel URL must use youtube.com")
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if not parts:
        raise ValueError("YouTube channel URL does not contain a channel identifier")
    kind = parts[0].lower()
    if kind == "channel":
        if len(parts) < 2 or not YOUTUBE_CHANNEL_ID.fullmatch(parts[1]):
            raise ValueError("YouTube channel ID is invalid")
        return parts[1]
    if kind in {"c", "user"}:
        if len(parts) < 2:
            raise ValueError("YouTube channel URL does not contain a name")
        return f"{kind}/{_youtube_identifier(parts[1])}"
    if parts[0].startswith("@"):
        return _youtube_identifier(parts[0])
    # YouTube also supports the historical short custom URL form
    # youtube.com/CustomName, which redirects to the canonical channel URL.
    return f"custom/{_youtube_identifier(parts[0])}"


def normalize_account(provider: str, value: str) -> str:
    if provider not in PROVIDERS:
        raise ValueError("Unsupported provider")
    if provider == "youtube":
        return _normalize_youtube_account(value)
    candidate = value.strip()
    if candidate.startswith(("http://", "https://")):
        parsed = urlparse(candidate)
        parts = [part for part in parsed.path.split("/") if part]
        candidate = parts[-1] if parts else ""
    candidate = candidate.strip().lstrip("@")
    candidate = candidate.lower()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", candidate):
        raise ValueError("Account ID or handle is invalid")
    return candidate


def default_templates(provider: str, events: list[str] | tuple[str, ...] | None = None) -> dict[str, dict[str, Any]]:
    selected = events or PROVIDER_EVENTS[provider]
    values: dict[str, dict[str, Any]] = {}
    for event in selected:
        live_end = event == "live_end"
        values[event] = {
            "content": "",
            "title": "{account} の配信は終了しました" if live_end else "{title}",
            "description": "{account} の配信は終了しました。" if live_end else "{account} が更新しました。\n{url}",
            "color": "#5865F2",
            "url": "{url}",
            "thumbnail_url": "{avatar}",
            "image_url": "{thumbnail}",
            "footer": "{platform} · {event}",
        }
    return values


def validate_templates(provider: str, templates: Any, events: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(templates, dict):
        raise ValueError("templates")
    defaults = default_templates(provider, events)
    result: dict[str, dict[str, Any]] = {}
    limits = {"content": 1900, "title": 256, "description": 4096, "url": 500, "thumbnail_url": 500, "image_url": 500, "footer": 2048}
    for event in events:
        supplied = templates.get(event) or {}
        if not isinstance(supplied, dict):
            raise ValueError("template")
        template = {**defaults[event], **supplied}
        for key, limit in limits.items():
            value = str(template.get(key, ""))
            if len(value) > limit:
                raise ValueError(f"template.{event}.{key}")
            unknown = set(UNKNOWN_VARIABLE_PATTERN.findall(value)) - set(TEMPLATE_VARIABLES)
            if unknown:
                raise ValueError(f"Unknown template variable: {sorted(unknown)[0]}")
            template[key] = value
        color = str(template.get("color", "#5865F2"))
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("template color")
        template["color"] = color.upper()
        sample_urls = {name: "https://example.com/value" for name in TEMPLATE_VARIABLES}
        for key in ("url", "thumbnail_url", "image_url"):
            rendered = render_template(template[key], sample_urls, limit=500).strip()
            if rendered and urlparse(rendered).scheme not in {"http", "https"}:
                raise ValueError(f"template.{event}.{key}")
        result[event] = template
    return result


def render_template(value: str, payload: dict[str, Any], *, limit: int) -> str:
    rendered = VARIABLE_PATTERN.sub(lambda match: str(payload.get(match.group(1), "") or ""), value)
    return rendered[:limit]


def validate_subscription(provider: str, body: dict[str, Any]) -> dict[str, Any]:
    account_key = normalize_account(provider, str(body.get("account", "")))
    events = [str(item) for item in body.get("events", [])]
    if not events:
        events = [item for item in PROVIDER_EVENTS[provider] if item != "live_end"]
    if len(events) != len(set(events)) or not set(events).issubset(PROVIDER_EVENTS[provider]):
        raise ValueError("events")
    channel_id = int(body["channel_id"])
    role_id = int(body["role_id"]) if body.get("role_id") else None
    raw_channels = body.get("event_channels") or {}
    if not isinstance(raw_channels, dict):
        raise ValueError("event_channels")
    event_channels = {str(key): int(value) for key, value in raw_channels.items() if value not in (None, "")}
    if not set(event_channels).issubset(events):
        raise ValueError("event_channels")
    return {
        "account_key": account_key,
        "channel_id": channel_id,
        "role_id": role_id,
        "events": events,
        "event_channels": event_channels,
        "templates": validate_templates(provider, body.get("templates") or {}, events),
        "enabled": bool(body.get("enabled", True)),
    }
