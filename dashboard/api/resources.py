"""Shared guild resource snapshot and membership checks."""
from __future__ import annotations
from typing import Any
from dashboard.discord_api import ADMINISTRATOR, PERMISSION_BITS
from .serialization import _resource_kind

def validate_resource_ids(settings: dict[str, Any], channels: set[int], roles: set[int]) -> None:
    for key, value in settings.items():
        if value in (None, '', []):
            continue
        kind = _resource_kind(key)
        if kind is None:
            continue
        resource_ids, multiple = (channels if kind[0] == 'channel' else roles, kind[1])
        values = value if multiple else [value]
        if not isinstance(values, list) or any((int(item) not in resource_ids for item in values)):
            raise ValueError(key)

class GuildResources:
    """Index one Discord response; callers choose freshness and domain constraints."""

    def __init__(self, channels: list[dict[str, Any]], roles: list[dict[str, Any]], permissions: int):
        self.channels = {int(item['id']): item for item in channels}
        self.role_ids = {int(item['id']) for item in roles}
        self.permissions = permissions

    def channel_ids(self, *types: int) -> set[int]:
        return {key for key, item in self.channels.items()
                if not types or int(item.get('type', -1)) in types}

    def missing_permissions(self, names) -> list[str]:
        if self.permissions & ADMINISTRATOR:
            return []
        return [name for name in names if not self.permissions & PERMISSION_BITS[name]]

    @classmethod
    async def fetch(cls, discord, guild_id: int, *, live: bool = True) -> GuildResources:
        return cls(*await discord.guild_resources(guild_id, use_cache=not live))
