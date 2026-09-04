"""Typed validation and normalization for Reaction Roles."""
from __future__ import annotations

import re
import unicodedata
from typing import Any


BEHAVIOR_TYPES = frozenset({"normal", "unique", "verify", "binding", "drop", "reversed", "temp"})
LINKABLE_TYPES = frozenset({"normal", "unique", "temp"})
CUSTOM_EMOJI = re.compile(r"^<(?P<animated>a?):(?P<name>[A-Za-z0-9_]{2,32}):(?P<id>[0-9]{15,22})>$")
EMOJI_BASE_RANGES = (
    (0x1F000, 0x1FAFF), (0x231A, 0x231B), (0x23E9, 0x23F3), (0x23F8, 0x23FA),
    (0x25AA, 0x25AB), (0x25FB, 0x25FE), (0x2600, 0x2604), (0x2614, 0x2615),
    (0x2622, 0x2623), (0x262E, 0x262F), (0x2638, 0x263A), (0x2648, 0x2653),
    (0x265F, 0x2660), (0x2665, 0x2666), (0x267E, 0x267F), (0x2692, 0x2697),
    (0x269B, 0x269C), (0x26A0, 0x26A1), (0x26AA, 0x26AB), (0x26BD, 0x26BE),
    (0x26C4, 0x26C5), (0x26CE, 0x26CF), (0x26D3, 0x26D4), (0x26E9, 0x26EA),
    (0x26F2, 0x26F5), (0x26F7, 0x26FA), (0x2708, 0x270D), (0x2733, 0x2734),
    (0x2753, 0x2755), (0x2795, 0x2797), (0x2B05, 0x2B07), (0x2B1B, 0x2B1C),
)
EMOJI_BASE_POINTS = {
    0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x2328, 0x23CF,
    0x24C2, 0x25B6, 0x25C0, 0x260E, 0x2611, 0x2618, 0x261D, 0x2620,
    0x2626, 0x262A, 0x2640, 0x2642, 0x2663, 0x2668, 0x267B, 0x2699,
    0x26A7, 0x26B0, 0x26B1, 0x26C8, 0x26D1, 0x26FD, 0x2702, 0x2705,
    0x270F, 0x2712, 0x2714, 0x2716, 0x271D, 0x2721, 0x2728, 0x2744,
    0x2747, 0x274C, 0x274E, 0x2757, 0x2763, 0x2764, 0x27A1, 0x27B0,
    0x27BF, 0x2934, 0x2935, 0x2B50, 0x2B55, 0x3030, 0x303D, 0x3297, 0x3299,
}


def _is_emoji_base(character: str) -> bool:
    point = ord(character)
    if 0x1F1E6 <= point <= 0x1F1FF or 0x1F3FB <= point <= 0x1F3FF:
        return False
    return point in EMOJI_BASE_POINTS or any(start <= point <= end for start, end in EMOJI_BASE_RANGES)


def _is_unicode_emoji(value: str) -> bool:
    points = [ord(character) for character in value]
    if len(points) == 2 and all(0x1F1E6 <= point <= 0x1F1FF for point in points):
        return True
    if len(points) in {2, 3} and points[0] in {*range(0x30, 0x3A), 0x23, 0x2A} and points[-1] == 0x20E3:
        return len(points) == 2 or points[1] == 0xFE0F
    if len(points) >= 3 and points[0] == 0x1F3F4 and points[-1] == 0xE007F:
        return all(0xE0020 <= point <= 0xE007E for point in points[1:-1])

    index = 0
    while index < len(value):
        if not _is_emoji_base(value[index]):
            return False
        index += 1
        if index < len(value) and ord(value[index]) in {0xFE0E, 0xFE0F}:
            index += 1
        if index < len(value) and 0x1F3FB <= ord(value[index]) <= 0x1F3FF:
            index += 1
        if index == len(value):
            return True
        if ord(value[index]) != 0x200D:
            return False
        index += 1
    return False
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class ReactionRoleValidationError(ValueError):
    def __init__(self, code: str, message: str, path: str = "") -> None:
        super().__init__(message)
        self.code, self.message, self.path = code, message, path


def normalize_emoji(value: str) -> dict[str, Any]:
    raw = str(value or "").strip()
    match = CUSTOM_EMOJI.fullmatch(raw)
    if match:
        emoji_id = int(match.group("id"))
        return {
            "key": f"custom:{emoji_id}", "display": raw, "emoji_id": emoji_id,
            "emoji_name": match.group("name"), "animated": bool(match.group("animated")),
        }
    normalized = unicodedata.normalize("NFC", raw)
    if not normalized or len(normalized) > 32 or not _is_unicode_emoji(normalized):
        raise ReactionRoleValidationError("emoji_invalid", "標準絵文字またはこのサーバーの絵文字を選択してください。", "mappings.emoji")
    return {"key": f"unicode:{normalized}", "display": normalized, "emoji_id": None, "emoji_name": None, "animated": False}


def default_message() -> dict[str, Any]:
    return {
        "name": "Reaction Roles", "source": "bot", "channel_id": None, "message_id": None,
        "behavior_type": "normal", "locked": False, "selection_limit": None,
        "temp_duration_seconds": None, "self_destruct_at": None, "enabled": True,
        "embed": {"title": "ロールを選択", "description": "リアクションを付けてロールを選択してください。", "color": "#5865F2"},
        "mappings": [], "whitelist_role_ids": [], "blacklist_role_ids": [], "link_group_id": None,
        "access_policy": "blacklist",
    }


def _snowflake(value: Any, path: str, *, optional: bool = False) -> int | None:
    if optional and value in (None, ""):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ReactionRoleValidationError("resource_invalid", "Discordリソースを選択してください。", path) from exc
    if result <= 0:
        raise ReactionRoleValidationError("resource_invalid", "Discordリソースを選択してください。", path)
    return result


def validate_message(raw: dict[str, Any], *, max_mappings: int = 20) -> dict[str, Any]:
    value = default_message()
    value.update({key: raw[key] for key in value if key in raw and key not in {"embed", "mappings", "whitelist_role_ids", "blacklist_role_ids"}})
    value["name"] = str(value["name"] or "").strip()[:100]
    if not value["name"]:
        raise ReactionRoleValidationError("name_required", "設定名を入力してください。", "name")
    if value["source"] not in {"bot", "external"}:
        raise ReactionRoleValidationError("source_invalid", "投稿元を確認してください。", "source")
    value["channel_id"] = _snowflake(value.get("channel_id"), "channel_id")
    value["message_id"] = _snowflake(value.get("message_id"), "message_id", optional=value["source"] == "bot")
    if value["source"] == "external" and value["message_id"] is None:
        raise ReactionRoleValidationError("message_required", "既存メッセージを選択してください。", "message_id")
    behavior = str(value.get("behavior_type") or "normal")
    if behavior not in BEHAVIOR_TYPES:
        raise ReactionRoleValidationError("type_invalid", "Typeを確認してください。", "behavior_type")
    value["behavior_type"] = behavior
    value["locked"] = bool(value.get("locked", False))
    value["enabled"] = bool(value.get("enabled", True))
    limit = value.get("selection_limit")
    value["selection_limit"] = None if limit in (None, "") else int(limit)
    if value["selection_limit"] is not None and not 1 <= value["selection_limit"] <= max_mappings:
        raise ReactionRoleValidationError("limit_invalid", f"選択上限は1～{max_mappings}で指定してください。", "selection_limit")
    if behavior in {"unique", "binding"}:
        if value["selection_limit"] not in (None, 1):
            raise ReactionRoleValidationError("limit_conflict", "このTypeの選択上限は1です。", "selection_limit")
        value["selection_limit"] = 1
    duration = value.get("temp_duration_seconds")
    value["temp_duration_seconds"] = None if duration in (None, "") else int(duration)
    if behavior == "temp" and (value["temp_duration_seconds"] is None or not 60 <= value["temp_duration_seconds"] <= 31_536_000):
        raise ReactionRoleValidationError("duration_invalid", "一時Roleの期間は1分～365日で指定してください。", "temp_duration_seconds")
    if behavior != "temp":
        value["temp_duration_seconds"] = None
    self_destruct = value.get("self_destruct_at")
    value["self_destruct_at"] = None if self_destruct in (None, "") else int(self_destruct)
    if value["source"] == "external" and value["self_destruct_at"] is not None:
        raise ReactionRoleValidationError("external_destructive", "外部投稿には自動削除を設定できません。", "self_destruct_at")

    embed = {**default_message()["embed"], **dict(raw.get("embed") or {})}
    embed["title"] = str(embed.get("title") or "")[:256]
    embed["description"] = str(embed.get("description") or "")[:4000]
    embed["color"] = str(embed.get("color") or "#5865F2").upper()
    if not HEX_COLOR.fullmatch(embed["color"]):
        raise ReactionRoleValidationError("color_invalid", "色は#RRGGBB形式で指定してください。", "embed.color")
    value["embed"] = embed

    mappings = list(raw.get("mappings") or [])
    if not 1 <= len(mappings) <= max_mappings:
        raise ReactionRoleValidationError("mapping_count", f"対応は1～{max_mappings}件で設定してください。", "mappings")
    emoji_keys: set[str] = set()
    role_ids: set[int] = set()
    normalized_mappings: list[dict[str, Any]] = []
    for index, mapping in enumerate(mappings):
        emoji = normalize_emoji(str(mapping.get("emoji") or mapping.get("display") or ""))
        role_id = _snowflake(mapping.get("role_id"), f"mappings.{index}.role_id")
        if emoji["key"] in emoji_keys:
            raise ReactionRoleValidationError("emoji_duplicate", "同じEmojiを複数登録できません。", f"mappings.{index}.emoji")
        if role_id in role_ids:
            raise ReactionRoleValidationError("role_duplicate", "同じRoleを複数登録できません。", f"mappings.{index}.role_id")
        cap = mapping.get("max_members")
        cap = None if cap in (None, "") else int(cap)
        if cap is not None and not 1 <= cap <= 1_000_000:
            raise ReactionRoleValidationError("max_members_invalid", "Role人数上限を確認してください。", f"mappings.{index}.max_members")
        emoji_keys.add(emoji["key"]); role_ids.add(role_id)
        normalized_mappings.append({**emoji, "role_id": role_id, "max_members": cap, "position": index})
    value["mappings"] = normalized_mappings
    for key in ("whitelist_role_ids", "blacklist_role_ids"):
        values = [_snowflake(item, key) for item in raw.get(key, [])]
        if len(values) != len(set(values)):
            raise ReactionRoleValidationError("access_duplicate", "同じRoleが重複しています。", key)
        value[key] = values
    requested_policy = raw.get("access_policy")
    if requested_policy in (None, ""):
        requested_policy = "whitelist" if value["whitelist_role_ids"] and not value["blacklist_role_ids"] else "blacklist"
    if requested_policy not in {"whitelist", "blacklist"}:
        raise ReactionRoleValidationError("access_policy_invalid", "アクセス方式を選択してください。", "access_policy")
    value["access_policy"] = requested_policy
    if value["whitelist_role_ids"] and value["blacklist_role_ids"]:
        raise ReactionRoleValidationError("access_conflict", "許可方式と拒否方式は同時に設定できません。", "access_policy")
    inactive_key = "blacklist_role_ids" if requested_policy == "whitelist" else "whitelist_role_ids"
    if value[inactive_key]:
        raise ReactionRoleValidationError("access_policy_conflict", "選択したアクセス方式とRole設定が一致していません。", inactive_key)
    link_group_id = value.get("link_group_id")
    value["link_group_id"] = None if link_group_id in (None, "") else int(link_group_id)
    if value["link_group_id"] is not None and behavior not in LINKABLE_TYPES:
        raise ReactionRoleValidationError("link_type_conflict", "このTypeはLink Groupへ追加できません。", "link_group_id")
    return value
