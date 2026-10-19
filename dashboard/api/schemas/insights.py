"""Aggregate-only Insights responses; no observer token or member identifiers."""
from typing import Literal
from pydantic import Field
from .base import ApiModel


class InsightsConfig(ApiModel):
    channel_ids: list[str] = Field(default_factory=list, max_length=25)
    retention_days: int = Field(default=30, strict=True, ge=1, le=365)
    track_members: bool = Field(default=True, strict=True)


class InsightsSettingsInput(ApiModel):
    enabled: bool = Field(strict=True)
    settings: InsightsConfig
    revision: int = Field(strict=True, ge=0)


class InsightsSettings(ApiModel):
    enabled: bool
    settings: InsightsConfig
    revision: int


class InsightsDay(ApiModel):
    day: str
    observed: bool
    messages: int | None
    joins: int | None
    leaves: int | None
    voice_seconds: int | None
    observed_seconds: int | None
    first_observed: int | None
    last_observed: int | None


class InsightsReport(ApiModel):
    enabled: bool
    collecting: bool
    timezone: Literal['UTC']
    retention_days: int
    last_observed: int | None
    days: list[InsightsDay]
