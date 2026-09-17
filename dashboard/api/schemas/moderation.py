"""moderation HTTP schemas."""
from __future__ import annotations
from typing import Any, Literal
from .base import ApiModel


class ModerationEvent(ApiModel):
    id: int
    guild_id: str
    actor_id: str | None = None
    target_id: str | None = None
    family: str
    event_type: str
    source: str
    target_user_id: str | None = None
    channel_id: str | None = None
    reason: str
    mode: str
    case_id: int | None = None
    created_at: int


class Rule(ApiModel):
    id: int = None
    guild_id: str = None
    family: str
    event_type: str
    name: str
    enabled: bool
    mode: Literal["monitor"] | Literal["enforce"]
    priority: int
    stop_on_match: bool
    trigger_type: str
    trigger_config: dict[str, Any]
    conditions: dict[str, Any]
    exemptions: dict[str, Any]
    actions: list[dict[str, Any]]
    revision: int = None


from .common import Items


class RulesResponse(Items[Rule]):
    trigger_types: list[str]


class RulePreview(ApiModel):
    matched: bool
    reason: str
    trace: list[str]


class ModerationCase(ApiModel):
    id: int
    guild_id: str
    user_id: str
    moderator_id: str | None
    action: str
    reason: str | None
    expires_at: int | None
    dm_sent: bool
    created_at: int
    source: str
    points: int
    revoked_at: int | None
    moderation_event_id: int | None
    moderation_rule_id: int | None


class Lockdown(ApiModel):
    id: int
    guild_id: str
    source_event_id: int | None
    status: str
    reason: str | None
    started_by: str | None
    started_at: int
    unlock_at: int | None
    completed_at: int | None
    last_error: str | None


class ModerationOverview(ApiModel):
    summary: dict[str, Any]
    events: list[ModerationEvent]
    lockdown: Lockdown | None


class InfractionsResponse(ApiModel):
    user_id: str
    active_points: int
    cases: list[ModerationCase]


class ActionResponse(ApiModel):
    request_id: int
    status: str
