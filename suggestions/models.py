"""Validation and defaults for guild suggestion settings."""
from __future__ import annotations

from typing import Any


class SuggestionValidationError(ValueError):
    """A dashboard-safe validation error with a field path."""

    def __init__(self, path: str, message: str) -> None:
        super().__init__(message)
        self.path = path


DEFAULT_SETTINGS: dict[str, Any] = {
    "channel_id": None,
    "log_channel_id": None,
    "review_role_ids": [],
    "allow_voting": True,
    "show_author": True,
    "form_title": "アイデアを投稿",
    "form_fields": [
        {
            "key": "idea",
            "label": "提案内容",
            "placeholder": "改善したいことや新しいアイデアを入力してください。",
            "style": "paragraph",
            "required": True,
            "min_length": 1,
            "max_length": 1000,
        }
    ],
}


def normalize_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    """Return a complete, bounded settings object suitable for Discord modals."""
    source = dict(DEFAULT_SETTINGS)
    source.update(settings or {})
    for name in ("channel_id", "log_channel_id"):
        value = source.get(name)
        if value in (None, ""):
            source[name] = None
        elif str(value).isdigit():
            source[name] = int(value)
        else:
            raise SuggestionValidationError(name, "Discordチャンネルを選択してください。")

    roles: list[int] = []
    for value in source.get("review_role_ids") or []:
        if not str(value).isdigit():
            raise SuggestionValidationError("review_role_ids", "Discordロールを選択してください。")
        role_id = int(value)
        if role_id not in roles:
            roles.append(role_id)
    source["review_role_ids"] = roles[:25]
    source["allow_voting"] = bool(source.get("allow_voting", True))
    source["show_author"] = bool(source.get("show_author", True))
    source["form_title"] = str(source.get("form_title") or DEFAULT_SETTINGS["form_title"]).strip()[:45]
    if not source["form_title"]:
        raise SuggestionValidationError("form_title", "フォームタイトルを入力してください。")

    raw_fields = source.get("form_fields")
    if not isinstance(raw_fields, list) or not 1 <= len(raw_fields) <= 5:
        raise SuggestionValidationError("form_fields", "フォーム項目は1～5件必要です。")
    fields: list[dict[str, Any]] = []
    keys: set[str] = set()
    for index, raw in enumerate(raw_fields):
        if not isinstance(raw, dict):
            raise SuggestionValidationError(f"form_fields.{index}", "フォーム項目を確認してください。")
        key = str(raw.get("key") or f"field_{index + 1}").strip()[:40]
        label = str(raw.get("label") or "").strip()
        placeholder = str(raw.get("placeholder") or "").strip()[:100]
        style = str(raw.get("style") or "short")
        required = bool(raw.get("required", False))
        try:
            minimum = int(raw.get("min_length", 0))
            maximum = int(raw.get("max_length", 1000))
        except (TypeError, ValueError) as exc:
            raise SuggestionValidationError(f"form_fields.{index}.max_length", "文字数は整数で指定してください。") from exc
        if not key or key in keys:
            raise SuggestionValidationError(f"form_fields.{index}.key", "項目キーは重複できません。")
        if not 1 <= len(label) <= 45:
            raise SuggestionValidationError(f"form_fields.{index}.label", "ラベルは1～45文字で入力してください。")
        if style not in {"short", "paragraph"}:
            raise SuggestionValidationError(f"form_fields.{index}.style", "入力形式を選択してください。")
        if not 0 <= minimum <= maximum <= 4000 or (required and minimum < 1):
            raise SuggestionValidationError(f"form_fields.{index}.min_length", "文字数は0～4000文字の範囲で指定してください。")
        keys.add(key)
        fields.append({
            "key": key, "label": label, "placeholder": placeholder, "style": style,
            "required": required, "min_length": minimum, "max_length": maximum,
        })
    source["form_fields"] = fields
    return source
