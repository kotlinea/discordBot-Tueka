"""Contracts shared by durable outbox and schedule runners."""
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Claim:
    id: int
    owner: str
    token: str
    payload: dict[str, Any]
    attempt: int


@dataclass(frozen=True)
class Outcome:
    error: str | None = None
    retry: bool = False
    result: dict[str, Any] | None = None


class LostLease(RuntimeError):
    pass


class RetryJob(Exception):
    pass


class JobStore(Protocol):
    def claim(self, owner: str, *, lease_seconds: int = 60) -> Claim | None: ...
    def renew(self, claim: Claim, *, lease_seconds: int = 60) -> bool: ...
    def finish(self, claim: Claim, outcome: Outcome) -> bool: ...
    def purge(self, *, retention_seconds: int = 30 * 86400) -> int: ...
