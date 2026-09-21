"""External provider adapters used only by the social worker."""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import httpx



from .contracts import ProviderAdapter, PollResult, SocialEvent

def _entries_from_atom(text: str) -> list[dict[str, str]]:
    root = ET.fromstring(text)
    ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    values = []
    for entry in root.findall("atom:entry", ns):
        link = entry.find("atom:link", ns)
        values.append({
            "id": entry.findtext("yt:videoId", "", ns),
            "channel_id": entry.findtext("yt:channelId", "", ns),
            "title": entry.findtext("atom:title", "", ns),
            "account": entry.findtext("atom:author/atom:name", "", ns),
            "url": link.attrib.get("href", "") if link is not None else "",
            "published_at": entry.findtext("atom:published", "", ns),
        })
    return [item for item in values if item["id"]]


YOUTUBE_CHANNEL_ID = re.compile(r"UC[A-Za-z0-9_-]{22}")
YOUTUBE_RSS_RETRY_SECONDS = 6 * 60 * 60
YOUTUBE_CHANNEL_PATTERNS = (
    re.compile(r'"externalId"\s*:\s*"(UC[A-Za-z0-9_-]{22})"'),
    re.compile(r'<meta[^>]+itemprop=["\']channelId["\'][^>]+content=["\'](UC[A-Za-z0-9_-]{22})["\']', re.IGNORECASE),
    re.compile(r'"channelId"\s*:\s*"(UC[A-Za-z0-9_-]{22})"'),
    re.compile(r'"browseId"\s*:\s*"(UC[A-Za-z0-9_-]{22})"'),
    re.compile(r'/channel/(UC[A-Za-z0-9_-]{22})'),
)


def _youtube_channel_id_from_html(text: str) -> str | None:
    """Extract the owning channel ID from a public YouTube handle page."""
    document = text[:2_000_000]
    for pattern in YOUTUBE_CHANNEL_PATTERNS:
        if match := pattern.search(document):
            return match.group(1)
    return None


class YouTubeAdapter(ProviderAdapter):
    provider = "youtube"

    @staticmethod
    def _public_channel_url(locator: str) -> str:
        if YOUTUBE_CHANNEL_ID.fullmatch(locator):
            path = f"channel/{locator}"
        elif locator.startswith("c/"):
            path = f"c/{quote(locator[2:], safe='._-')}"
        elif locator.startswith("user/"):
            path = f"user/{quote(locator[5:], safe='._-')}"
        elif locator.startswith("custom/"):
            path = quote(locator[7:], safe="._-")
        else:
            path = f"@{quote(locator, safe='._-')}"
        return f"https://www.youtube.com/{path}"

    async def _public_channel_page(self, locator: str) -> str:
        url = self._public_channel_url(locator)
        for _ in range(4):
            response = await self.client.get(url)
            if response.status_code not in {301, 302, 303, 307, 308}:
                response.raise_for_status()
                return response.text
            location = response.headers.get("location")
            if not location:
                break
            next_url = urljoin(url, location)
            parsed = urlparse(next_url)
            host = (parsed.hostname or "").lower().rstrip(".")
            if parsed.scheme != "https" or (host != "youtube.com" and not host.endswith(".youtube.com")):
                raise ValueError("YouTube以外へのリダイレクトは使用できません。")
            url = next_url
        raise ValueError("YouTubeチャンネルURLのリダイレクトを解決できませんでした。")

    async def _resolve_channel_id(self, locator: str) -> str:
        if self.settings.youtube_api_key and not locator.startswith(("c/", "custom/")):
            parameter = "forUsername" if locator.startswith("user/") else "forHandle"
            identifier = locator[5:] if parameter == "forUsername" else locator
            resolved = await self.client.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "snippet", parameter: identifier, "key": self.settings.youtube_api_key})
            resolved.raise_for_status()
            items = resolved.json().get("items", [])
            if items:
                return str(items[0]["id"])

        # A handle page contains its canonical UC channel identifier. This keeps
        # RSS/WebSub registration usable without requiring a Data API quota.
        # The URL host is fixed; only the already-normalized handle is encoded.
        try:
            page = await self._public_channel_page(locator)
        except httpx.HTTPStatusError as exc:
            # Older custom channel URLs can exist at /name while /@name is a
            # different (or unclaimed) handle. Try that documented legacy URL
            # only after the handle-shaped URL explicitly returns 404.
            is_plain_locator = not locator.startswith(("c/", "user/", "custom/")) and not YOUTUBE_CHANNEL_ID.fullmatch(locator)
            if exc.response.status_code != 404 or not is_plain_locator:
                raise
            page = await self._public_channel_page(f"custom/{locator}")
        channel_id = _youtube_channel_id_from_html(page)
        if not channel_id:
            raise ValueError("YouTubeチャンネルが見つかりません。ハンドルまたはチャンネルIDを確認してください。")
        return channel_id

    async def _data_api_entries(self, channel_id: str) -> tuple[list[dict[str, str]], str | None, str | None]:
        """Read recent uploads through the official API when the public RSS endpoint is unavailable."""
        channel_response = await self.client.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "snippet,contentDetails", "id": channel_id, "key": self.settings.youtube_api_key},
        )
        channel_response.raise_for_status()
        channels = channel_response.json().get("items", [])
        if not channels:
            raise ValueError("YouTubeチャンネルが見つかりません。チャンネルIDを確認してください。")
        channel = channels[0]
        snippet = channel.get("snippet") or {}
        uploads_id = ((channel.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads")
        if not uploads_id:
            return [], snippet.get("title"), ((snippet.get("thumbnails") or {}).get("default") or {}).get("url")
        uploads_response = await self.client.get(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={"part": "snippet,contentDetails", "playlistId": uploads_id, "maxResults": 15, "key": self.settings.youtube_api_key},
        )
        uploads_response.raise_for_status()
        entries: list[dict[str, str]] = []
        for item in uploads_response.json().get("items", []):
            item_snippet = item.get("snippet") or {}
            video_id = str((item.get("contentDetails") or {}).get("videoId") or (item_snippet.get("resourceId") or {}).get("videoId") or "")
            if not video_id:
                continue
            entries.append({
                "id": video_id,
                "channel_id": channel_id,
                "title": str(item_snippet.get("title") or ""),
                "account": str(item_snippet.get("channelTitle") or snippet.get("title") or channel_id),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "published_at": str(item_snippet.get("publishedAt") or ""),
            })
        avatar = ((snippet.get("thumbnails") or {}).get("default") or {}).get("url")
        return entries, snippet.get("title"), avatar

    async def _yt_dlp_entries(self, channel_id: str) -> tuple[list[dict[str, str]], str | None] | None:
        """Best-effort public-page fallback used only while YouTube RSS returns 404/5xx."""
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "yt_dlp", "--flat-playlist", "--dump-single-json",
            "--playlist-end", "15", "--skip-download", "--no-warnings",
            f"https://www.youtube.com/channel/{channel_id}/videos",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        except TimeoutError:
            process.kill()
            await process.communicate()
            return None
        if process.returncode or len(stdout) > 2_000_000:
            return None
        try:
            data = json.loads(stdout)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        account = str(data.get("channel") or data.get("uploader") or data.get("title") or channel_id)
        entries: list[dict[str, str]] = []
        for item in data.get("entries") or []:
            video_id = str(item.get("id") or "")
            if not video_id:
                continue
            entries.append({
                "id": video_id,
                "channel_id": channel_id,
                "title": str(item.get("title") or ""),
                "account": str(item.get("channel") or item.get("uploader") or account),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "published_at": str(item.get("timestamp") or item.get("release_timestamp") or item.get("upload_date") or ""),
            })
        return entries[:15], account

    async def _channel_exists_publicly(self, channel_id: str) -> bool:
        page_id = _youtube_channel_id_from_html(await self._public_channel_page(channel_id))
        return page_id == channel_id

    async def _sync_websub(self, channel_id: str, cursor: dict[str, Any]) -> str | None:
        if not self.settings.dashboard_base_url or int(cursor.get("websub_renew_at") or 0) > int(time.time()):
            return None
        data = {
            "hub.mode": "subscribe",
            "hub.topic": f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
            "hub.callback": f"{self.settings.dashboard_base_url.rstrip('/')}/webhooks/youtube",
            "hub.verify": "async",
        }
        if self.settings.social_webhook_secret:
            data["hub.secret"] = self.settings.social_webhook_secret
        try:
            subscribed = await self.client.post("https://pubsubhubbub.appspot.com/subscribe", data=data, timeout=10.0)
            subscribed.raise_for_status()
        except httpx.HTTPError as exc:
            # WebSub is the low-latency path. A timeout or hub failure must not
            # discard a successful RSS poll; the worker will retry on the next
            # shortened polling interval.
            return f"YouTube WebSub購読を完了できませんでした（{type(exc).__name__}）。RSS監視を継続して再試行します。"
        cursor["websub_renew_at"] = int(time.time()) + 345600
        return None

    async def poll(self, target: dict[str, Any], *, initialize: bool) -> PollResult:
        account_key = str(target["account_key"])
        channel_id = str(target.get("external_id") or account_key)
        requested_handle = target.get("handle") or (account_key if not YOUTUBE_CHANNEL_ID.fullmatch(account_key) else None)
        if not YOUTUBE_CHANNEL_ID.fullmatch(channel_id):
            channel_id = await self._resolve_channel_id(channel_id)
        cursor_before = target.get("cursor", {})
        entries: list[dict[str, str]]
        api_name: str | None = None
        api_avatar: str | None = None
        now = int(time.time())
        rss_retry_at = int(cursor_before.get("rss_retry_at") or 0)
        rss_status_code = int(cursor_before.get("rss_last_status") or 404)
        rss_unavailable = rss_retry_at > now
        rss_failure: httpx.HTTPStatusError | None = None
        source = "rss"
        if not rss_unavailable:
            try:
                response = await self.client.get("https://www.youtube.com/feeds/videos.xml", params={"channel_id": channel_id})
                response.raise_for_status()
                entries = _entries_from_atom(response.text)
                rss_retry_at = 0
                rss_status_code = 0
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code != 404 and status_code < 500:
                    raise
                rss_failure = exc
                rss_status_code = status_code
                rss_retry_at = now + YOUTUBE_RSS_RETRY_SECONDS
                rss_unavailable = True
        if rss_unavailable:
            if self.settings.youtube_api_key:
                entries, api_name, api_avatar = await self._data_api_entries(channel_id)
                source = "youtube_api"
            else:
                public_fallback = await self._yt_dlp_entries(channel_id)
                if public_fallback is not None:
                    entries, api_name = public_fallback
                    source = "public_metadata"
                else:
                    entries = []
                if public_fallback is not None:
                    # Continue through the normal cursor/event path. WebSub is
                    # still synchronized below for the low-latency path.
                    pass
                else:
                    # Only repeat the page existence check when this request
                    # first opens the RSS circuit. Subsequent retries already
                    # have a resolved, verified channel ID.
                    if rss_failure is not None and not await self._channel_exists_publicly(channel_id):
                        raise ValueError("YouTubeチャンネルが見つかりません。チャンネルIDを確認してください。") from rss_failure
                    # A valid channel can temporarily return 404/5xx from the
                    # RSS endpoint and the public fallback can also be blocked.
                    # Preserve an established cursor, or mark a new one for a
                    # no-notification baseline when either source recovers.
                    recovery_cursor = dict(cursor_before)
                    recovery_cursor.setdefault("seen", [])
                    recovery_cursor.setdefault("live_ids", [])
                    recovery_cursor.setdefault("websub_renew_at", 0)
                    recovery_cursor["feed_ready"] = bool(cursor_before.get("seen"))
                    recovery_cursor["rss_retry_at"] = rss_retry_at
                    recovery_cursor["rss_last_status"] = rss_status_code
                    recovery_cursor["source"] = "unavailable"
                    websub_error = await self._sync_websub(channel_id, recovery_cursor)
                    rss_error = f"YouTube RSSが一時的に利用できません（HTTP {rss_status_code}）。代替経路を使用して再確認します。"
                    return PollResult(
                        cursor=recovery_cursor,
                        external_id=channel_id,
                        handle=requested_handle or channel_id,
                        display_name=target.get("display_name") or channel_id,
                        avatar_url=target.get("avatar_url"),
                        interval_seconds=120,
                        status="pending" if initialize else "degraded",
                        error=" ".join(part for part in (rss_error, websub_error) if part),
                    )
        previous = set(cursor_before.get("seen", []))
        current = [item["id"] for item in entries[:15]]
        video_state: dict[str, dict[str, Any]] = {}
        if self.settings.youtube_api_key and current:
            details = await self.client.get("https://www.googleapis.com/youtube/v3/videos", params={"part": "snippet,liveStreamingDetails", "id": ",".join(current), "key": self.settings.youtube_api_key})
            details.raise_for_status()
            video_state = {str(item["id"]): item for item in details.json().get("items", [])}
        previous_live = set(cursor_before.get("live_ids", []))
        live_ids = {video_id for video_id,item in video_state.items() if item.get("liveStreamingDetails", {}).get("actualStartTime") and not item.get("liveStreamingDetails", {}).get("actualEndTime")}
        events: list[SocialEvent] = []
        effective_initialize = initialize or cursor_before.get("feed_ready") is False
        if not effective_initialize:
            for item in reversed(entries):
                state = video_state.get(item["id"], {})
                live_details = state.get("liveStreamingDetails") or {}
                if item["id"] in live_ids and item["id"] not in previous_live:
                    event_type = "live_start"
                elif item["id"] in previous_live and live_details.get("actualEndTime"):
                    event_type = "live_end"
                elif item["id"] not in previous and not live_details:
                    event_type = "video"
                else:
                    continue
                events.append(SocialEvent(item["id"], event_type, {"account": item["account"], "handle": target.get("handle") or channel_id,
                    "title": item["title"], "text": "", "url": item["url"], "platform": "YouTube", "event": event_type,
                    "published_at": live_details.get("actualStartTime") or item["published_at"],
                    "thumbnail": f"https://i.ytimg.com/vi/{item['id']}/maxresdefault.jpg", "avatar": target.get("avatar_url") or "",
                    "viewer_count": live_details.get("concurrentViewers", "")}))
        name = api_name or (entries[0]["account"] if entries else target.get("display_name") or channel_id)
        cursor = {
            "seen": current,
            "live_ids": sorted(live_ids),
            "websub_renew_at": cursor_before.get("websub_renew_at", 0),
            "feed_ready": True,
            "rss_retry_at": rss_retry_at,
            "rss_last_status": rss_status_code,
            "source": source,
        }
        websub_error = await self._sync_websub(channel_id, cursor)
        interval = 300 if source != "rss" else (120 if self.settings.youtube_api_key or websub_error else 600)
        return PollResult(
            cursor, events, channel_id, requested_handle or channel_id, name,
            api_avatar or target.get("avatar_url"), interval,
            "degraded" if websub_error else "active", websub_error,
        )

    async def unsubscribe(self, target: dict[str, Any]) -> None:
        if not self.settings.dashboard_base_url:
            return
        channel_id = target.get("external_id") or target["account_key"]
        data = {"hub.mode": "unsubscribe", "hub.topic": f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
                "hub.callback": f"{self.settings.dashboard_base_url.rstrip('/')}/webhooks/youtube", "hub.verify": "async"}
        if self.settings.social_webhook_secret:
            data["hub.secret"] = self.settings.social_webhook_secret
        response = await self.client.post("https://pubsubhubbub.appspot.com/subscribe", data=data)
        response.raise_for_status()
