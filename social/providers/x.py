"""External provider adapters used only by the social worker."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote




from .contracts import ProviderAdapter, PollResult, SocialEvent

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
            user_path = f"users/{quote(handle)}" if handle.isdecimal() else f"users/by/username/{quote(handle)}"
            response = await self.client.get(f"https://api.x.com/2/{user_path}", params={"user.fields": "name,profile_image_url,username"}, headers=headers)
            response.raise_for_status()
            user = response.json().get("data") or {}
            if not user.get("id"):
                raise ValueError("X account was not found")
            external_id, handle, display_name, avatar = user["id"], user.get("username", handle), user.get("name", handle), user.get("profile_image_url")
        params = {"max_results": 10 if initialize else 100, "exclude": "replies,retweets", "tweet.fields": "created_at,attachments,text"}
        since_id = target.get("cursor", {}).get("since_id")
        if since_id:
            params["since_id"] = since_id
        posts, identifiers, page_tokens = [], set(), set()
        while True:
            response = await self.client.get(f"https://api.x.com/2/users/{external_id}/tweets", params=params, headers=headers)
            response.raise_for_status()
            page = response.json()
            items = page.get("data") or []
            if page.get("errors") or not isinstance(items, list):
                raise RuntimeError("X returned an incomplete posts response")
            for item in items:
                if not isinstance(item, dict) or not item.get("id"):
                    raise RuntimeError("X returned a post without an identity")
                identifier = str(item["id"])
                if identifier not in identifiers:
                    identifiers.add(identifier)
                    posts.append(item)
            next_token = (page.get("meta") or {}).get("next_token")
            if initialize or not next_token:
                break
            if next_token in page_tokens:
                raise RuntimeError("X pagination repeated a page token")
            page_tokens.add(next_token)
            params["pagination_token"] = next_token
        newest = posts[0]["id"] if posts else since_id
        events = [] if initialize else [SocialEvent(post["id"], "post", {
            "account": display_name or handle, "handle": handle, "title": f"@{handle} の新しい投稿", "text": post.get("text", ""),
            "url": f"https://x.com/{handle}/status/{post['id']}", "platform": "X", "event": "post", "published_at": post.get("created_at", ""),
            "thumbnail": "", "avatar": avatar or "", "viewer_count": "",
        }) for post in reversed(posts)]
        return PollResult({"since_id": newest}, events, str(external_id), str(handle), str(display_name or handle), avatar, 60)
