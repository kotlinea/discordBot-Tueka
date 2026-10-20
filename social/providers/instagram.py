"""External provider adapters used only by the social worker."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote, urlparse




from .contracts import ProviderAdapter, PollResult, SocialEvent

def _entries_from_rss(text: str) -> list[dict[str, str]]:
    root = ET.fromstring(text)
    entries = []
    seen = set()
    for item in root.findall(".//item"):
        url = item.findtext("link", "").strip()
        identifier = item.findtext("guid", "").strip() or url
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        enclosure = item.find("enclosure")
        entries.append({"id": identifier, "title": item.findtext("title", "Instagram post"), "text": item.findtext("description", ""), "url": url,
                        "published_at": item.findtext("pubDate", ""), "thumbnail": enclosure.attrib.get("url", "") if enclosure is not None else "",
                        "event": "reel" if "/reel/" in url else "post"})
    return [item for item in entries if item["id"]]


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
        current = [item["id"] for item in entries] or list(target.get("cursor", {}).get("seen", []))
        # RSS is newest first. A known post marks the existing snapshot's boundary,
        # including older items omitted by the historical twenty-ID checkpoint.
        new_entries = []
        for item in entries:
            if item["id"] in previous:
                break
            new_entries.append(item)
        events = [] if initialize else [SocialEvent(item["id"], item.get("event", "post"), {
            "account": item.get("account") or target["account_key"], "handle": target["account_key"], "title": item["title"], "text": item.get("text", ""),
            "url": item["url"], "platform": "Instagram", "event": item.get("event", "post"), "published_at": item.get("published_at", ""),
            "thumbnail": item.get("thumbnail", ""), "avatar": target.get("avatar_url") or "", "viewer_count": "",
        }) for item in reversed(new_entries)]
        return PollResult({"seen": current}, events, target["account_key"], target["account_key"], target.get("display_name") or target["account_key"], target.get("avatar_url"), 120)
