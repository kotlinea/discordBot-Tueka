"""Manager-only campaign and participant-history wire contracts."""
from typing import Literal, Any
from pydantic import Field
from .base import ApiModel


class GiveawayConfig(ApiModel):
    kind: Literal['giveaway', 'event'] = 'giveaway'
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default='', max_length=2000)
    channel_id: str
    ends_at: int = Field(strict=True, ge=1)
    winner_count: int = Field(default=1, strict=True, ge=0, le=20)
    capacity: int = Field(default=1000, strict=True, ge=1, le=1000)
    required_role_ids: list[str] = Field(default_factory=list, max_length=25)
    denied_role_ids: list[str] = Field(default_factory=list, max_length=25)
    min_account_days: int = Field(default=0, strict=True, ge=0, le=3650)
    min_member_days: int = Field(default=0, strict=True, ge=0, le=3650)
    retention_days: int = Field(default=30, strict=True, ge=1, le=365)


class GiveawayCreateInput(ApiModel):
    config: GiveawayConfig
    request_key: str = Field(min_length=1, max_length=100)


class GiveawayEditInput(ApiModel):
    config: GiveawayConfig
    revision: int = Field(strict=True, ge=1)


class GiveawayRevisionInput(ApiModel):
    revision: int = Field(strict=True, ge=1)


class GiveawayReasonInput(GiveawayRevisionInput):
    reason: str = Field(min_length=1, max_length=500)


class GiveawayItem(ApiModel):
    id: int
    guild_id: str
    actor_id: str
    config: GiveawayConfig
    status: Literal['draft', 'open', 'closing', 'closed', 'cancelled']
    revision: int
    message_id: str | None
    delivery_started: bool
    round_number: int
    ends_at: int
    created_at: int
    updated_at: int
    expires_at: int


class GiveawayEntry(ApiModel):
    campaign_id: int
    user_id: str
    active: bool
    joined_at: int
    updated_at: int


class GiveawayDraw(ApiModel):
    id: int
    campaign_id: int
    round_number: int
    actor_id: str
    reason: str
    candidates: list[str]
    winners: list[str]
    excluded_count: int
    candidate_hash: str
    created_at: int


class GiveawayEvent(ApiModel):
    id: int
    campaign_id: int
    actor_id: str
    event_type: str
    detail: dict[str, Any]
    created_at: int


class GiveawayJob(ApiModel):
    id: int
    status: str
    attempts: int
    last_error: str | None
    round_number: int | None = None


class GiveawayHistory(ApiModel):
    events: list[GiveawayEvent]
    draws: list[GiveawayDraw]
    entries: list[GiveawayEntry]
    delivery: list[GiveawayJob]
    draw_jobs: list[GiveawayJob]
