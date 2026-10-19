"""External provider adapters used only by the social worker."""
from __future__ import annotations

import time
from typing import Any




from .contracts import ProviderAdapter, PollResult, SocialEvent

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
        identity = {"id": target['external_id']} if target.get('external_id') else {"login": target['account_key']}
        user_response = await self.client.get("https://api.twitch.tv/helix/users", params=identity, headers=headers)
        user_response.raise_for_status()
        users = user_response.json().get("data", [])
        if not users:
            raise ValueError("Twitch account was not found")
        user = users[0]
        if target.get('external_id') and str(user['id']) != str(target['external_id']):
            raise RuntimeError('Twitch account identity did not match the monitored user')
        stream_response = await self.client.get("https://api.twitch.tv/helix/streams", params={"user_id": user["id"]}, headers=headers)
        stream_response.raise_for_status()
        streams = stream_response.json().get("data", [])
        live, was_live = bool(streams), bool(target.get("cursor", {}).get("live"))
        previous_id = target.get('cursor', {}).get('stream_id')
        stream_id = streams[0].get('id') if streams else None
        changed = live and was_live and previous_id and stream_id and str(previous_id) != str(stream_id)
        events: list[SocialEvent] = []
        transitions = []
        if not initialize:
            if was_live and (not live or changed):
                transitions.append(('live_end', {}, previous_id))
            if live and (not was_live or changed):
                transitions.append(('live_start', streams[0], stream_id))
        for event_type, stream, event_id in transitions:
            events.append(SocialEvent(str(event_id or int(time.time())), event_type, {
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
