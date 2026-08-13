"""Boundary for a future Discord-native AutoMod synchronization adapter."""
from __future__ import annotations

from typing import Any, Protocol


class NativeAutoModAdapter(Protocol):
    async def upsert(self, guild_id: int, rule: dict[str, Any]) -> str | None: ...
    async def delete(self, guild_id: int, external_rule_id: str) -> None: ...


def discord_compatible(rule: dict[str, Any]) -> bool:
    """Return whether the internal rule could be represented by Discord today."""
    supported_triggers = {"keyword", "regex", "mention_rate"}
    supported_actions = {"delete", "timeout", "log"}
    return rule.get("trigger_type") in supported_triggers and all(action.get("type") in supported_actions for action in rule.get("actions", []))
