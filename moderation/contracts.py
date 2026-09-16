"""Discord-independent values and operations consumed by moderation services."""
from dataclasses import dataclass
from typing import Any, Protocol
from discord_io import DiscordFailure as ActionFailure


@dataclass(frozen=True)
class GuildRef:
    id: int
    name: str = ''


@dataclass(frozen=True)
class MemberRef:
    id: int
    guild_id: int
    name: str = ''

    @property
    def mention(self) -> str:
        return f'<@{self.id}>'

    def __str__(self) -> str:
        return self.name or str(self.id)


@dataclass(frozen=True)
class ChannelRef:
    id: int
    name: str = ''

    @property
    def mention(self) -> str:
        return f'<#{self.id}>'


@dataclass(frozen=True)
class MessageRef:
    id: int
    channel: ChannelRef


@dataclass(frozen=True)
class ActionContext:
    guild: GuildRef
    member: MemberRef | None = None
    message: MessageRef | None = None
    channel: ChannelRef | None = None
    reaction: str | None = None
    actor: MemberRef | None = None


class ModerationPort(Protocol):
    async def unban(self, guild_id: int, user_id: int, reason: str | None) -> None: ...
    def manageable(self, actor: MemberRef | None, target: MemberRef, action: str) -> str | None: ...
    async def dm(self, member: MemberRef, text: str) -> bool: ...
    async def member_action(self, guild_id: int, user_id: int, action: str, reason: str | None, duration_minutes: int, execution_id: int) -> None: ...
    async def applied(self, guild_id: int, user_id: int, action: str, expires_at: int | None, execution_id: int, created_at: int) -> bool | None: ...
    async def send(self, channel_id: int, *, content: str | None = None, embed: dict[str, Any] | None = None) -> None: ...
    async def perform(self, context: ActionContext, action: dict[str, Any], reason: str) -> dict[str, Any]: ...
    def lockdown_snapshots(self, guild_id: int, channel_ids: list[int], category_ids: list[int]) -> list[dict[str, Any]]: ...
    async def set_overwrite(self, guild_id: int, channel_id: int, role_id: int, values: dict[str, bool | None], reason: str) -> None: ...
    def overwrite(self, guild_id: int, channel_id: int, role_id: int) -> dict[str, bool | None] | None: ...
