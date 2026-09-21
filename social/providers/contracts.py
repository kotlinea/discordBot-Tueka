"""External provider adapters used only by the social worker."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from config import Settings


@dataclass
class SocialEvent:
    external_id: str
    event_type: str
    payload: dict[str, Any]
    occurred_at: int | None = None


@dataclass
class PollResult:
    cursor: dict[str, Any]
    events: list[SocialEvent] = field(default_factory=list)
    external_id: str | None = None
    handle: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    interval_seconds: int = 120
    status: str = "active"
    error: str | None = None


class ProviderAdapter:
    provider = ""

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings, self.client = settings, client

    async def poll(self, target: dict[str, Any], *, initialize: bool) -> PollResult:
        raise NotImplementedError

    async def unsubscribe(self, target: dict[str, Any]) -> None:
        return None
