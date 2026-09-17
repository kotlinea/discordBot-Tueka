"""social HTTP schemas."""
from __future__ import annotations
from typing import Any, Literal
from .base import ApiModel
from pydantic import Field


class SocialTemplate(ApiModel):
    content: str = Field(max_length=1900)
    title: str = Field(max_length=256)
    description: str = Field(max_length=4096)
    color: str
    url: str
    thumbnail_url: str
    image_url: str
    footer: str = Field(max_length=2048)


class SocialTarget(ApiModel):
    id: int
    provider: str
    account_key: str
    external_id: str | None = None
    handle: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    status: Literal["pending"] | Literal["active"] | Literal["degraded"] | Literal["error"]
    last_error: str | None = None
    last_checked_at: int | None = None
    revision: int


class SocialSubscription(ApiModel):
    id: int
    provider: str
    account_id: str
    channel_id: str
    role_id: str | None
    events: list[str]
    event_channels: dict[str, str]
    templates: dict[str, SocialTemplate]
    enabled: bool
    status: str
    last_error: str | None = None
    revision: int
    target: SocialTarget | None


class SocialProviderSummary(ApiModel):
    id: str
    available: bool
    events: list[str]
    count: int
    limit: int


from .common import Items


class SocialSummary(ApiModel):
    providers: list[SocialProviderSummary]
    worker: dict[str, Any]


class SocialSubscriptions(Items[SocialSubscription]):
    available: bool
    events: list[str]
    limit: int
    variables: list[str]
    defaults: dict[str, SocialTemplate]
