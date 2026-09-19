"""Encrypted transcript and attachment blob storage."""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


@dataclass(frozen=True)
class StoredTranscript:
    backend: str
    object_key: str
    content_hash: str
    byte_size: int


class TranscriptStorage:
    def __init__(self, base_dir: str | Path, encryption_key: str | None, *, s3: dict[str, str | None] | None = None) -> None:
        self.base_dir = Path(base_dir)
        self._cipher = Fernet(encryption_key.encode("ascii")) if encryption_key else None
        self.s3 = s3 or {}

    @property
    def available(self) -> bool:
        return self._cipher is not None

    def encrypt_text(self, value: str) -> str:
        if self._cipher is None:
            raise RuntimeError("TICKET_ENCRYPTION_KEY is not configured")
        return self._cipher.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt_text(self, value: str | None) -> str:
        if not value:
            return ""
        if self._cipher is None:
            raise RuntimeError("TICKET_ENCRYPTION_KEY is not configured")
        try:
            return self._cipher.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Encrypted ticket content could not be verified") from exc

    def _encrypted_blob(self, payload: dict[str, Any]) -> tuple[bytes, str]:
        if self._cipher is None:
            raise RuntimeError("TICKET_ENCRYPTION_KEY is not configured")
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        compressed = gzip.compress(raw, compresslevel=6)
        digest = hashlib.sha256(raw).hexdigest()
        return self._cipher.encrypt(compressed), digest

    def _local_path(self, object_key: str) -> Path:
        path = (self.base_dir / object_key).resolve()
        if self.base_dir.resolve() not in path.parents:
            raise ValueError("Invalid transcript object key")
        return path

    async def save(self, guild_id: int, ticket_id: int, payload: dict[str, Any]) -> StoredTranscript:
        encrypted, digest = self._encrypted_blob(payload)
        object_key = f"{guild_id}/{ticket_id}/{digest[:16]}.ticket"
        path = self._local_path(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        temporary.write_bytes(encrypted)
        os.replace(temporary, path)
        if self.s3.get("bucket"):
            try:
                await asyncio.to_thread(self._upload_s3, object_key, encrypted)
                return StoredTranscript("s3", object_key, digest, len(encrypted))
            except Exception:
                # The encrypted local copy is intentionally retained as the
                # durable fallback. A later maintenance pass may promote it.
                pass
        return StoredTranscript("local", object_key, digest, len(encrypted))

    async def save_attachment(self, guild_id: int, ticket_id: int, attachment_id: int, data: bytes) -> StoredTranscript:
        if self._cipher is None:
            raise RuntimeError("TICKET_ENCRYPTION_KEY is not configured")
        if len(data) > 25 * 1024 * 1024:
            raise ValueError("attachment_too_large")
        digest = hashlib.sha256(data).hexdigest()
        encrypted = self._cipher.encrypt(data)
        object_key = f"{guild_id}/{ticket_id}/attachments/{attachment_id}-{digest[:16]}.attachment"
        path = self._local_path(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        temporary.write_bytes(encrypted)
        os.replace(temporary, path)
        if self.s3.get("bucket"):
            try:
                await asyncio.to_thread(self._upload_s3, object_key, encrypted)
                return StoredTranscript("s3", object_key, digest, len(data))
            except Exception:
                pass
        return StoredTranscript("local", object_key, digest, len(data))

    async def load_attachment(self, backend: str, object_key: str, expected_hash: str) -> bytes:
        if backend == "s3":
            try:
                encrypted = await asyncio.to_thread(self._download_s3, object_key)
            except Exception:
                encrypted = self._local_path(object_key).read_bytes()
        else:
            encrypted = self._local_path(object_key).read_bytes()
        if self._cipher is None:
            raise RuntimeError("TICKET_ENCRYPTION_KEY is not configured")
        try:
            raw = self._cipher.decrypt(encrypted)
        except InvalidToken as exc:
            raise ValueError("Attachment integrity check failed") from exc
        if hashlib.sha256(raw).hexdigest() != expected_hash:
            raise ValueError("Attachment hash mismatch")
        return raw

    def _client(self):
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 is required for S3 transcript storage") from exc
        return boto3.client("s3", endpoint_url=self.s3.get("endpoint_url") or None, region_name=self.s3.get("region") or None,
                            aws_access_key_id=self.s3.get("access_key_id") or None, aws_secret_access_key=self.s3.get("secret_access_key") or None)

    def _s3_key(self, object_key: str) -> str:
        prefix = str(self.s3.get("prefix") or "ticket-transcripts").strip("/")
        return f"{prefix}/{object_key}"

    def _upload_s3(self, object_key: str, encrypted: bytes) -> None:
        client, key = self._client(), self._s3_key(object_key)
        client.put_object(Bucket=self.s3["bucket"], Key=key, Body=encrypted,
                          ContentType="application/octet-stream", Metadata={"encrypted": "fernet-v1"})
        head = client.head_object(Bucket=self.s3["bucket"], Key=key)
        if int(head.get("ContentLength", -1)) != len(encrypted):
            raise IOError("S3 transcript integrity check failed")

    async def promote_local(self, object_key: str) -> None:
        if not self.s3.get("bucket"):
            raise RuntimeError("S3 transcript storage is not configured")
        encrypted = self._local_path(object_key).read_bytes()
        await asyncio.to_thread(self._upload_s3, object_key, encrypted)

    async def load(self, backend: str, object_key: str, expected_hash: str) -> dict[str, Any]:
        if backend == "s3":
            try:
                encrypted = await asyncio.to_thread(self._download_s3, object_key)
            except Exception:
                encrypted = self._local_path(object_key).read_bytes()
        else:
            encrypted = self._local_path(object_key).read_bytes()
        if self._cipher is None:
            raise RuntimeError("TICKET_ENCRYPTION_KEY is not configured")
        try:
            raw = gzip.decompress(self._cipher.decrypt(encrypted))
        except (InvalidToken, OSError) as exc:
            raise ValueError("Transcript integrity check failed") from exc
        if not hashlib.sha256(raw).hexdigest() == expected_hash:
            raise ValueError("Transcript hash mismatch")
        return json.loads(raw)

    def _download_s3(self, object_key: str) -> bytes:
        return self._client().get_object(Bucket=self.s3["bucket"], Key=self._s3_key(object_key))["Body"].read()

    async def delete(self, backend: str, object_key: str) -> None:
        path = self._local_path(object_key)
        if path.exists():
            path.unlink()
        if backend == "s3" and self.s3.get("bucket"):
            await asyncio.to_thread(self._client().delete_object, Bucket=self.s3["bucket"], Key=self._s3_key(object_key))
