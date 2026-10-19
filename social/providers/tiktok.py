"""External provider adapters used only by the social worker."""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any




from .contracts import ProviderAdapter, PollResult, SocialEvent

class TikTokAdapter(ProviderAdapter):
    provider = "tiktok"

    async def _extract(self, url: str, *, flat: bool = False, offline_ok: bool = False) -> dict[str, Any] | None:
        arguments = [sys.executable, "-m", "yt_dlp"]
        if flat:
            arguments += ["--flat-playlist", "--playlist-end", "10"]
        arguments += ["--dump-single-json", "--skip-download", "--no-warnings", url]
        process = await asyncio.create_subprocess_exec(*arguments, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=25)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeError("TikTok check timed out")
        error_text = stderr.decode("utf-8", "replace")
        if process.returncode:
            if offline_ok and any(marker in error_text.lower() for marker in ("not live", "offline", "no video", "currently unavailable")):
                return None
            raise RuntimeError((error_text or "TikTok check failed")[:300])
        if len(stdout) > 2_000_000:
            raise RuntimeError("TikTok response was too large")
        return json.loads(stdout)

    async def poll(self, target: dict[str, Any], *, initialize: bool) -> PollResult:
        handle = target["account_key"]
        data = await self._extract(f"https://www.tiktok.com/@{handle}", flat=True) or {}
        entries = data.get("entries") or []
        if not isinstance(entries, list):
            raise RuntimeError("TikTok returned an invalid entries response")
        entries = [item for item in entries if isinstance(item, dict) and item.get("id")]
        previous = set(target.get("cursor", {}).get("seen", []))
        current = [str(item.get("id")) for item in entries if item.get("id")][:20]
        events = [] if initialize else [SocialEvent(str(item["id"]), "post", {
            "account": data.get("uploader") or handle, "handle": handle, "title": item.get("title") or f"@{handle} の新しい投稿",
            "text": item.get("description", ""), "url": item.get("url") or item.get("webpage_url") or f"https://www.tiktok.com/@{handle}/video/{item['id']}",
            "platform": "TikTok", "event": "post", "published_at": item.get("timestamp", ""), "thumbnail": item.get("thumbnail", ""),
            "avatar": target.get("avatar_url") or "", "viewer_count": "",
        }) for item in reversed(entries) if str(item.get("id")) not in previous]
        live_data = await self._extract(f"https://www.tiktok.com/@{handle}/live", offline_ok=True)
        live = bool(live_data and (live_data.get("is_live") or live_data.get("live_status") == "is_live"))
        was_live = bool(target.get("cursor", {}).get("live"))
        live_id = str((live_data or {}).get("id") or target.get("cursor", {}).get("live_id") or handle)
        if not initialize and live != was_live:
            event_type = "live_start" if live else "live_end"
            events.append(SocialEvent(live_id, event_type, {"account": data.get("uploader") or handle, "handle": handle,
                "title": (live_data or {}).get("title") or f"@{handle} の配信", "text": (live_data or {}).get("description", ""),
                "url": f"https://www.tiktok.com/@{handle}/live", "platform": "TikTok", "event": event_type,
                "published_at": (live_data or {}).get("timestamp", ""), "thumbnail": (live_data or {}).get("thumbnail", ""),
                "avatar": target.get("avatar_url") or "", "viewer_count": (live_data or {}).get("concurrent_view_count", "")}))
        return PollResult({"seen": current, "live": live, "live_id": live_id}, events, handle, handle, data.get("uploader") or handle, target.get("avatar_url"), 60 if live else 120)
