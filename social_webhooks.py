"""Provider webhook authentication kept independent from FastAPI."""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone


def verify_youtube_signature(body: bytes, supplied: str, secret: str) -> bool:
    expected = "sha1=" + hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()
    return bool(supplied) and hmac.compare_digest(supplied, expected)


def verify_twitch_signature(body: bytes, message_id: str, timestamp: str, supplied: str, secret: str, *, now: datetime | None = None) -> bool:
    try:
        sent_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        current = now or datetime.now(timezone.utc)
        if sent_at.tzinfo is None or abs((current - sent_at).total_seconds()) > 600:
            return False
    except (TypeError, ValueError):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), (message_id + timestamp).encode() + body, hashlib.sha256).hexdigest()
    return bool(message_id and supplied) and hmac.compare_digest(supplied, expected)
