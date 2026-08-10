"""Encryption boundary for third-party OAuth tokens.

Only encrypted values cross into SQLite.  Keeping this tiny module separate
makes accidental plaintext persistence easy to spot in review.
"""
from cryptography.fernet import Fernet, InvalidToken


class SocialTokenCipher:
    def __init__(self, key: str | None) -> None:
        self._fernet = Fernet(key.encode("ascii")) if key else None

    @property
    def available(self) -> bool:
        return self._fernet is not None

    def encrypt(self, token: str) -> str:
        if not self._fernet:
            raise RuntimeError("SOCIAL_TOKEN_ENCRYPTION_KEY is not configured")
        return self._fernet.encrypt(token.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        if not self._fernet:
            raise RuntimeError("SOCIAL_TOKEN_ENCRYPTION_KEY is not configured")
        try:
            return self._fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Invalid encrypted social token") from exc
