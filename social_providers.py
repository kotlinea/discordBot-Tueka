"""External provider adapters used only by the social worker."""
from __future__ import annotations

import asyncio
import json
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlparse

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


class ProviderAdapter:
    provider = ""

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings, self.client = settings, client

    async def poll(self, target: dict[str, Any], *, initialize: bool) -> PollResult:
        raise NotImplementedError

    async def unsubscribe(self, target: dict[str, Any]) -> None:
        return None


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


class YouTubeAdapter(ProviderAdapter):
    provider = "youtube"

    async def poll(self, target: dict[str, Any], *, initialize: bool) -> PollResult:
        channel_id = target.get("external_id") or target["account_key"]
        if not str(channel_id).startswith("UC"):
            if not self.settings.youtube_api_key:
                raise RuntimeError("YouTube handles require YOUTUBE_API_KEY; use a channel ID instead")
            resolved = await self.client.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "snippet", "forHandle": channel_id, "key": self.settings.youtube_api_key})
            resolved.raise_for_status()
            items = resolved.json().get("items", [])
            if not items:
                raise ValueError("YouTube channel was not found")
            channel_id = items[0]["id"]
        response = await self.client.get("https://www.youtube.com/feeds/videos.xml", params={"channel_id": channel_id})
        response.raise_for_status()
        entries = _entries_from_atom(response.text)
        previous = set(target.get("cursor", {}).get("seen", []))
        current = [item["id"] for item in entries[:15]]
        video_state: dict[str, dict[str, Any]] = {}
        if self.settings.youtube_api_key and current:
            details = await self.client.get("https://www.googleapis.com/youtube/v3/videos", params={"part": "snippet,liveStreamingDetails", "id": ",".join(current), "key": self.settings.youtube_api_key})
            details.raise_for_status()
            video_state = {str(item["id"]): item for item in details.json().get("items", [])}
        previous_live = set(target.get("cursor", {}).get("live_ids", []))
        live_ids = {video_id for video_id,item in video_state.items() if item.get("liveStreamingDetails", {}).get("actualStartTime") and not item.get("liveStreamingDetails", {}).get("actualEndTime")}
        events: list[SocialEvent] = []
        if not initialize:
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
        name = entries[0]["account"] if entries else target.get("display_name") or channel_id
        cursor = {"seen": current, "live_ids": sorted(live_ids), "websub_renew_at": target.get("cursor", {}).get("websub_renew_at", 0)}
        if self.settings.dashboard_base_url and int(cursor["websub_renew_at"] or 0) <= int(time.time()):
            data = {"hub.mode": "subscribe", "hub.topic": f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}",
                    "hub.callback": f"{self.settings.dashboard_base_url.rstrip('/')}/webhooks/youtube", "hub.verify": "async"}
            if self.settings.social_webhook_secret:
                data["hub.secret"] = self.settings.social_webhook_secret
            subscribed = await self.client.post("https://pubsubhubbub.appspot.com/subscribe", data=data)
            subscribed.raise_for_status()
            cursor["websub_renew_at"] = int(time.time()) + 345600
        return PollResult(cursor, events, channel_id, target.get("handle") or channel_id, name, target.get("avatar_url"), 120 if self.settings.youtube_api_key else 600)

    async def unsubscribe(self, target: dict[str, Any]) -> None:
        if not self.settings.dashboard_base_url:
            return
        channel_id = target.get("external_id") or target["account_key"]
        data = {"hub.mode": "unsubscribe", "hub.topic": f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}",
                "hub.callback": f"{self.settings.dashboard_base_url.rstrip('/')}/webhooks/youtube", "hub.verify": "async"}
        if self.settings.social_webhook_secret:
            data["hub.secret"] = self.settings.social_webhook_secret
        response = await self.client.post("https://pubsubhubbub.appspot.com/subscribe", data=data)
        response.raise_for_status()


class TwitchAdapter(ProviderAdapter):
    provider = "twitch"

    async def _token(self) -> str:
        response = await self.client.post("https://id.twitch.tv/oauth2/token", params={"client_id": self.settings.twitch_client_id, "client_secret": self.settings.twitch_client_secret, "grant_type": "client_credentials"})
        response.raise_for_status()
        return str(response.json()["access_token"])

    async def poll(self, target: dict[str, Any], *, initialize: bool) -> PollResult:
        if not self.settings.twitch_client_id or not self.settings.twitch_client_secret:
            raise RuntimeError("Twitch credentials are not configured")
        token = await self._token()
        headers = {"Client-Id": self.settings.twitch_client_id, "Authorization": f"Bearer {token}"}
        user_response = await self.client.get("https://api.twitch.tv/helix/users", params={"login": target["account_key"]}, headers=headers)
        user_response.raise_for_status()
        users = user_response.json().get("data", [])
        if not users:
            raise ValueError("Twitch account was not found")
        user = users[0]
        stream_response = await self.client.get("https://api.twitch.tv/helix/streams", params={"user_id": user["id"]}, headers=headers)
        stream_response.raise_for_status()
        streams = stream_response.json().get("data", [])
        live, was_live = bool(streams), bool(target.get("cursor", {}).get("live"))
        events: list[SocialEvent] = []
        if not initialize and live != was_live:
            event_type = "live_start" if live else "live_end"
            stream = streams[0] if streams else {}
            events.append(SocialEvent(str(stream.get("id") or target.get("cursor", {}).get("stream_id") or int(time.time())), event_type, {
                "account": user["display_name"], "handle": user["login"], "title": stream.get("title") or f"{user['display_name']} の配信",
                "text": stream.get("game_name", ""), "url": f"https://twitch.tv/{user['login']}", "platform": "Twitch", "event": event_type,
                "published_at": stream.get("started_at", ""), "thumbnail": str(stream.get("thumbnail_url", "")).replace("{width}", "1280").replace("{height}", "720"),
                "avatar": user.get("profile_image_url", ""), "viewer_count": stream.get("viewer_count", ""),
            }))
        cursor = {"live": live, "stream_id": streams[0].get("id") if streams else target.get("cursor", {}).get("stream_id"),
                  "eventsub_synced_at": target.get("cursor", {}).get("eventsub_synced_at", 0)}
        if self.settings.dashboard_base_url and self.settings.social_webhook_secret and int(cursor["eventsub_synced_at"] or 0) < int(time.time()) - 86400:
            callback = f"{self.settings.dashboard_base_url.rstrip('/')}/webhooks/twitch"
            for event_type in ("stream.online", "stream.offline"):
                response = await self.client.post("https://api.twitch.tv/helix/eventsub/subscriptions", headers={**headers, "Content-Type": "application/json"}, json={
                    "type": event_type, "version": "1", "condition": {"broadcaster_user_id": str(user["id"])},
                    "transport": {"method": "webhook", "callback": callback, "secret": self.settings.social_webhook_secret},
                })
                if response.status_code not in {202, 409}:
                    response.raise_for_status()
            cursor["eventsub_synced_at"] = int(time.time())
        return PollResult(cursor, events, str(user["id"]), user["login"], user["display_name"], user.get("profile_image_url"), 300)

    async def unsubscribe(self, target: dict[str, Any]) -> None:
        if not self.settings.twitch_client_id or not self.settings.twitch_client_secret:
            return
        token = await self._token()
        headers = {"Client-Id": self.settings.twitch_client_id, "Authorization": f"Bearer {token}"}
        response = await self.client.get("https://api.twitch.tv/helix/eventsub/subscriptions", headers=headers)
        response.raise_for_status()
        external_id = str(target.get("external_id") or "")
        for item in response.json().get("data", []):
            if str((item.get("condition") or {}).get("broadcaster_user_id", "")) == external_id:
                deleted = await self.client.delete("https://api.twitch.tv/helix/eventsub/subscriptions", params={"id": item["id"]}, headers=headers)
                deleted.raise_for_status()


class XAdapter(ProviderAdapter):
    provider = "x"

    async def poll(self, target: dict[str, Any], *, initialize: bool) -> PollResult:
        if not self.settings.x_bearer_token:
            raise RuntimeError("X bearer token is not configured")
        headers = {"Authorization": f"Bearer {self.settings.x_bearer_token}"}
        external_id = target.get("external_id")
        handle = target.get("handle") or target["account_key"]
        display_name, avatar = target.get("display_name"), target.get("avatar_url")
        if not external_id:
            response = await self.client.get(f"https://api.x.com/2/users/by/username/{quote(handle)}", params={"user.fields": "name,profile_image_url,username"}, headers=headers)
            response.raise_for_status()
            user = response.json().get("data") or {}
            if not user.get("id"):
                raise ValueError("X account was not found")
            external_id, handle, display_name, avatar = user["id"], user.get("username", handle), user.get("name", handle), user.get("profile_image_url")
        params = {"max_results": 10, "exclude": "replies,retweets", "tweet.fields": "created_at,attachments,text"}
        since_id = target.get("cursor", {}).get("since_id")
        if since_id:
            params["since_id"] = since_id
        response = await self.client.get(f"https://api.x.com/2/users/{external_id}/tweets", params=params, headers=headers)
        response.raise_for_status()
        posts = response.json().get("data", [])
        newest = posts[0]["id"] if posts else since_id
        events = [] if initialize else [SocialEvent(post["id"], "post", {
            "account": display_name or handle, "handle": handle, "title": f"@{handle} の新しい投稿", "text": post.get("text", ""),
            "url": f"https://x.com/{handle}/status/{post['id']}", "platform": "X", "event": "post", "published_at": post.get("created_at", ""),
            "thumbnail": "", "avatar": avatar or "", "viewer_count": "",
        }) for post in reversed(posts)]
        return PollResult({"since_id": newest}, events, str(external_id), str(handle), str(display_name or handle), avatar, 60)


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


class InstagramAdapter(ProviderAdapter):
    provider = "instagram"

    async def poll(self, target: dict[str, Any], *, initialize: bool) -> PollResult:
        template = self.settings.instagram_rss_url_template
        if not template or "{account}" not in template:
            raise RuntimeError("Instagram RSS is not configured")
        url = template.replace("{account}", quote(target["account_key"], safe=""))
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise RuntimeError("Instagram RSS URL must use HTTPS")
        headers = {"Authorization": f"Bearer {self.settings.instagram_rss_auth_token}"} if self.settings.instagram_rss_auth_token else {}
        response = await self.client.get(url, headers=headers)
        response.raise_for_status()
        entries = _entries_from_rss(response.text)
        previous = set(target.get("cursor", {}).get("seen", []))
        current = [item["id"] for item in entries[:20]]
        events = [] if initialize else [SocialEvent(item["id"], item.get("event", "post"), {
            "account": item.get("account") or target["account_key"], "handle": target["account_key"], "title": item["title"], "text": item.get("text", ""),
            "url": item["url"], "platform": "Instagram", "event": item.get("event", "post"), "published_at": item.get("published_at", ""),
            "thumbnail": item.get("thumbnail", ""), "avatar": target.get("avatar_url") or "", "viewer_count": "",
        }) for item in reversed(entries) if item["id"] not in previous]
        return PollResult({"seen": current}, events, target["account_key"], target["account_key"], target.get("display_name") or target["account_key"], target.get("avatar_url"), 120)


def _entries_from_rss(text: str) -> list[dict[str, str]]:
    root = ET.fromstring(text)
    entries = []
    for item in root.findall(".//item"):
        url = item.findtext("link", "").strip()
        identifier = item.findtext("guid", "").strip() or url
        enclosure = item.find("enclosure")
        entries.append({"id": identifier, "title": item.findtext("title", "Instagram post"), "text": item.findtext("description", ""), "url": url,
                        "published_at": item.findtext("pubDate", ""), "thumbnail": enclosure.attrib.get("url", "") if enclosure is not None else "",
                        "event": "reel" if "/reel/" in url else "post"})
    return [item for item in entries if item["id"]]


def build_adapters(settings: Settings, client: httpx.AsyncClient) -> dict[str, ProviderAdapter]:
    return {item.provider: item(settings, client) for item in (YouTubeAdapter, TwitchAdapter, TikTokAdapter, XAdapter, InstagramAdapter)}
