"""Shared HTTP error envelopes without changing domain-specific messages."""
from typing import Any

from fastapi import HTTPException


def api_error(status: int, code: str, message: str, **details: Any) -> HTTPException:
    return HTTPException(status, detail={'code': code, 'message': message, **details})


def revision_conflict(message: str) -> HTTPException:
    return api_error(409, 'revision_conflict', message)


def check_revision(expected: int | str | None, current: int, message: str, *, required: bool = False) -> None:
    if expected is None:
        if required:
            raise revision_conflict(message)
        return
    try:
        value = int(str(expected).strip('"'))
    except (TypeError, ValueError) as exc:
        raise api_error(422, 'revision_invalid', 'revisionまたはIf-Matchを確認してください。') from exc
    if value != current:
        raise revision_conflict(message)
