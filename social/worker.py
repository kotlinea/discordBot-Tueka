"""Standalone social-provider monitor process."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import socket
import time
from typing import Any

import httpx

from config import Settings
from social.providers.contracts import PollResult
from social.providers.registry import build_adapters
from social import SocialRepository
from observability.heartbeat import ServiceHeartbeat
from observability.logging import configure_logging
from observability.metrics import registry


log = logging.getLogger("tueka.social_worker")


class SocialWorker:
    def __init__(self, settings: Settings, *, clock=time.monotonic) -> None:
        self.settings = settings
        self.repository = SocialRepository(settings.database_url)
        self.owner = f"{socket.gethostname()}:{os.getpid()}"
        self.failures: dict[str, int] = {}
        self._clock = clock
        self._next_purge_at = clock() + 3600

    def _purge_history_if_due(self) -> None:
        if self._clock() < self._next_purge_at:
            return
        try:
            self.repository.purge_social_history(retention_days=30)
        except Exception:
            log.warning("Social history cleanup failed", exc_info=True)
        finally:
            self._next_purge_at = self._clock() + 3600

    async def _process_target(self, target: dict[str, Any], adapters: dict[str, Any]) -> None:
        provider = target["provider"]
        adapter = adapters[provider]
        if target["status"] == "orphaned":
            try:
                await adapter.unsubscribe(target)
                self.repository.delete_social_target(target["id"], target["lease_owner"])
            except Exception as exc:
                self.repository.complete_social_target(target["id"], target["lease_owner"], status="orphaned", cursor=target.get("cursor", {}),
                    next_check_at=int(time.time()) + 3600, error=str(exc)[:500])
            return
        initialize = target["status"] == "pending" or not target.get("cursor")
        try:
            result: PollResult = await adapter.poll(target, initialize=initialize)
            account_id = result.external_id or target["account_key"]
            self.failures[provider] = 0
            interval = self.settings.social_poll_interval_seconds if provider in {"tiktok", "instagram"} and result.interval_seconds >= 120 else result.interval_seconds
            jitter = random.randint(0, max(1, interval // 10))
            self.repository.complete_social_target(target["id"], target["lease_owner"], status=result.status, cursor=result.cursor,
                next_check_at=int(time.time()) + interval + jitter, external_id=result.external_id, handle=result.handle,
                display_name=result.display_name, avatar_url=result.avatar_url, error=result.error,
                events=[{'external_id': event.external_id, 'account_id': account_id, 'event_type': event.event_type,
                         'payload': event.payload, 'occurred_at': event.occurred_at} for event in result.events])
        except Exception as exc:
            registry.add('provider_errors_total', provider=provider)
            failures = self.failures.get(provider, 0) + 1
            self.failures[provider] = failures
            delay = min(3600, 30 * (2 ** min(failures, 7))) + random.randint(0, 15)
            status = "error" if initialize else "degraded"
            self.repository.complete_social_target(target["id"], target["lease_owner"], status=status, cursor=target.get("cursor", {}),
                next_check_at=int(time.time()) + delay, error=str(exc)[:500])
            log.warning("social target check failed provider=%s target_id=%s error=%s", provider, target["id"], type(exc).__name__)

    async def poll_loop(self, client: httpx.AsyncClient) -> None:
        adapters = build_adapters(self.settings, client)
        semaphores = {provider: asyncio.Semaphore(2 if provider in {"tiktok", "instagram"} else 5) for provider in adapters}
        while True:
            targets = self.repository.claim_social_targets(self.owner, limit=5, lease_seconds=240)
            async def run(target: dict[str, Any]) -> None:
                async with semaphores[target["provider"]]:
                    await self._process_target(target, adapters)
            if targets:
                await asyncio.gather(*(run(target) for target in targets))
            else:
                await asyncio.sleep(2)
            self._purge_history_if_due()

    async def heartbeat_loop(self) -> None:
        while True:
            self.repository.social_worker_heartbeat(self.owner, {"provider_failures": self.failures, "x_mode": self.settings.social_x_mode})
            await asyncio.sleep(10)

    async def _replace_x_rules(self, client: httpx.AsyncClient) -> None:
        token = self.settings.x_bearer_token
        if not token:
            return
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        response = await client.get("https://api.x.com/2/tweets/search/stream/rules", headers=headers)
        response.raise_for_status()
        owned = [item["id"] for item in response.json().get("data", []) if str(item.get("tag", "")).startswith("tueka:")]
        if owned:
            delete = await client.post("https://api.x.com/2/tweets/search/stream/rules", headers=headers, json={"delete": {"ids": owned}})
            delete.raise_for_status()
        targets = [item for item in self.repository.social_targets("x") if item["status"] in {"active", "degraded"}]
        rules = [{"value": f"from:{item['handle'] or item['account_key']} -is:reply -is:retweet", "tag": f"tueka:{item['id']}"} for item in targets[:1000]]
        if rules:
            add = await client.post("https://api.x.com/2/tweets/search/stream/rules", headers=headers, json={"add": rules})
            add.raise_for_status()

    async def x_stream_loop(self, client: httpx.AsyncClient) -> None:
        if self.settings.social_x_mode != "stream" or not self.settings.x_bearer_token:
            return
        headers = {"Authorization": f"Bearer {self.settings.x_bearer_token}"}
        backoff = 5
        while True:
            try:
                await self._replace_x_rules(client)
                async with asyncio.timeout(300):
                    async with client.stream("GET", "https://api.x.com/2/tweets/search/stream", headers=headers, params={"tweet.fields": "author_id,created_at"}) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            body = json.loads(line)
                            post = body.get("data") or {}
                            tags = [item.get("tag", "") for item in body.get("matching_rules", [])]
                            target_ids = [int(tag.split(":", 1)[1]) for tag in tags if tag.startswith("tueka:") and tag.split(":", 1)[1].isdigit()]
                            for target_id in target_ids:
                                target = self.repository.social_target(target_id)
                                if not target or not post.get("id"):
                                    continue
                                handle = target.get("handle") or target["account_key"]
                                payload = {"account": target.get("display_name") or handle, "handle": handle, "title": f"@{handle} の新しい投稿",
                                    "text": post.get("text", ""), "url": f"https://x.com/{handle}/status/{post['id']}", "platform": "X", "event": "post",
                                    "published_at": post.get("created_at", ""), "thumbnail": "", "avatar": target.get("avatar_url") or "", "viewer_count": ""}
                                self.repository.enqueue_social_event_v2("x", post["id"], str(target.get("external_id") or handle), "post", payload)
                backoff = 5
            except Exception as exc:
                log.warning("X stream disconnected error=%s", type(exc).__name__)
                await asyncio.sleep(backoff)
                backoff = min(300, backoff * 2)

    async def run(self) -> None:
        limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
        async with ServiceHeartbeat('social-worker', self.settings.database_url), httpx.AsyncClient(timeout=httpx.Timeout(20), limits=limits, follow_redirects=False, headers={"User-Agent": "Tueka-SocialWorker/1"}) as client:
            await asyncio.gather(self.poll_loop(client), self.x_stream_loop(client), self.heartbeat_loop())


async def main() -> None:
    settings = Settings.from_env()
    configure_logging('social-worker', settings.log_level)
    await SocialWorker(settings).run()


if __name__ == "__main__":
    from runtime.lifecycle import run
    run(main)
