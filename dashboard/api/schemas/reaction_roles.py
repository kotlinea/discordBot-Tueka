"""reaction_roles HTTP schemas."""
from __future__ import annotations
from typing import Any, Literal
from .base import ApiModel
from pydantic import Field


ReactionRoleBehavior = Literal["normal"] | Literal["unique"] | Literal["verify"] | Literal["binding"] | Literal["drop"] | Literal["reversed"] | Literal["temp"]


class ReactionRoleMapping(ApiModel):
    id: int = None
    emoji: str
    emoji_key: str = None
    emoji_id: str | None = None
    role_id: str
    max_members: int | None
    position: int = None


class ReactionRoleMessageEmbed(ApiModel):
    title: str = Field(max_length=256)
    description: str = Field(max_length=4096)
    color: str


class ReactionRoleMessage(ApiModel):
    id: int = None
    guild_id: str = None
    name: str
    source: Literal["bot"] | Literal["external"]
    channel_id: str | None
    message_id: str | None
    behavior_type: ReactionRoleBehavior
    locked: bool
    access_policy: Literal["whitelist"] | Literal["blacklist"]
    selection_limit: int | None
    temp_duration_seconds: int | None
    self_destruct_at: int | None
    embed: ReactionRoleMessageEmbed
    mappings: list[ReactionRoleMapping]
    whitelist_role_ids: list[str]
    blacklist_role_ids: list[str]
    link_group_id: int | None
    enabled: bool
    status: str = None
    last_error: str | None = None
    revision: int = None


class ReactionRoleSettings(ApiModel):
    guild_id: str
    enabled: bool
    log_channel_id: str | None
    denial_dm: bool
    denial_dm_cooldown_seconds: int
    audit_retention_days: int
    revision: int


class ReactionRoleEvent(ApiModel):
    id: int
    guild_id: str
    message_config_id: int | None = None
    user_id: str | None = None
    actor_id: str | None = None
    emoji_key: str | None = None
    role_id: str | None = None
    event_type: str
    result: str
    reason: str | None = None
    created_at: int


class ReactionRoleRecovery(ApiModel):
    deleted_message_id: str
    created_at: int
    expires_at: int


class ReactionRoleOverview(ApiModel):
    settings: ReactionRoleSettings
    items: list[ReactionRoleMessage]
    summary: dict[str, int]
    recoveries: list[ReactionRoleRecovery]


class ReactionRoleLinkGroup(ApiModel):
    id: int
    name: str
    message_ids: list[int]
