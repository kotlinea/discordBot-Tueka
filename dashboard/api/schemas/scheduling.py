"""Explicit scheduling contracts with string Discord identifiers."""
from typing import Literal
from pydantic import Field
from .base import ApiModel


class SchedulePayload(ApiModel):
    kind: Literal['message','event']
    title: str = Field(default='',max_length=100)
    body: str = Field(default='',max_length=2000)
    color: int = Field(default=0x5865F2,ge=0,le=0xFFFFFF)
    channel_id: str | None = None
    run_at: int
    interval_seconds: Literal[0,86400,604800] = 0
    occurrences: int = Field(default=1,ge=1,le=365)
    event_start: int | None = None
    event_end: int | None = None
    event_location: str | None = Field(default=None,max_length=100)


class ScheduleCreateInput(ApiModel):
    payload: SchedulePayload
    request_key: str = Field(min_length=1,max_length=100)


class ScheduleEditInput(ApiModel):
    payload: SchedulePayload
    revision: int = Field(ge=1)


class ScheduleRevisionInput(ApiModel):
    revision: int = Field(ge=1)


class ScheduleItem(ApiModel):
    id: int
    guild_id: str
    actor_id: str
    payload: SchedulePayload
    next_due: int
    remaining: int
    status: Literal['scheduled','completed','cancelled']
    revision: int
    retention_days: int
    created_at: int
    updated_at: int
    expires_at: int


class ScheduleEvent(ApiModel):
    id: int
    post_id: int
    actor_id: str
    event_type: str
    detail: str
    created_at: int


class ScheduleDelivery(ApiModel):
    id: int
    due_at: int
    deadline: int
    status: str
    attempts: int
    delivery_started: bool
    discord_receipt_id: str | None


class ScheduleHistory(ApiModel):
    events: list[ScheduleEvent]
    delivery: list[ScheduleDelivery]
