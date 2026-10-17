"""Discord REST client used by the dashboard, with safe GET-side caching."""
import asyncio
import math
import logging
import time
from typing import Any

import httpx

from dashboard.timing import add as add_timing


API_BASE = "https://discord.com/api/v10"


def retry_after(response: httpx.Response) -> float | None:
    """Read Discord's delay without accepting malformed/non-finite headers."""
    try:
        value = response.headers.get('Retry-After')
        if value is None:
            value = response.json().get('retry_after')
        delay = float(value)
        return delay if math.isfinite(delay) and delay >= 0 else None
    except (ValueError, TypeError, AttributeError):
        return None


ADMINISTRATOR = 0x8
MANAGEMENT_PERMISSIONS = 0x0000000000000008 | 0x0000000000000010 | 0x0000000000000020 | 0x0000000000000040 | 0x0000000000000080 | 0x0000000000000100 | 0x0000000000000400 | 0x0000000000001000 | 0x0000000000002000 | 0x0000000000004000 | 0x0000000000008000 | 0x0000000001000000 | 0x0000000020000000
PERMISSION_BITS = {
    "send_messages": 1 << 11, "view_audit_log": 1 << 7, "manage_messages": 1 << 13,
    "manage_channels": 1 << 4, "manage_roles": 1 << 28, "move_members": 1 << 24,
    "add_reactions": 1 << 6, "view_channel": 1 << 10,
    "moderate_members": 1 << 40, "kick_members": 1 << 1, "ban_members": 1 << 2,
    "read_message_history": 1 << 16, "embed_links": 1 << 14, "attach_files": 1 << 15,
    "manage_threads": 1 << 34, "create_public_threads": 1 << 35, "create_private_threads": 1 << 36, "send_messages_in_threads": 1 << 38,
}


def effective_channel_permissions(
    guild_id: int,
    bot_user_id: int,
    bot_role_ids: set[int],
    guild_permissions: int,
    overwrites: list[dict[str, Any]],
) -> int:
    """Resolve Discord channel overwrites for the dashboard's bot member."""
    if guild_permissions & ADMINISTRATOR:
        return (1 << 53) - 1

    permissions = guild_permissions
    everyone = next(
        (item for item in overwrites if int(item.get("type", -1)) == 0 and int(item.get("id", 0)) == guild_id),
        None,
    )
    if everyone:
        permissions &= ~int(everyone.get("deny", "0"))
        permissions |= int(everyone.get("allow", "0"))

    role_denies = role_allows = 0
    for item in overwrites:
        if int(item.get("type", -1)) == 0 and int(item.get("id", 0)) in bot_role_ids:
            role_denies |= int(item.get("deny", "0"))
            role_allows |= int(item.get("allow", "0"))
    permissions &= ~role_denies
    permissions |= role_allows

    member = next(
        (item for item in overwrites if int(item.get("type", -1)) == 1 and int(item.get("id", 0)) == bot_user_id),
        None,
    )
    if member:
        permissions &= ~int(member.get("deny", "0"))
        permissions |= int(member.get("allow", "0"))
    return permissions


class DiscordAPI:
    def __init__(self, bot_token: str, client_id: str, client_secret: str, redirect_uri: str) -> None:
        self.bot_token, self.client_id, self.client_secret, self.redirect_uri = bot_token, client_id, client_secret, redirect_uri
        self._client: httpx.AsyncClient | None = None
        self._cache: dict[tuple[str, str], tuple[float, Any]] = {}
        self._manageable_inflight: dict[str, asyncio.Task] = {}

    async def start(self) -> None:
        await self._client_or_create()

    async def close(self) -> None:
        pending = tuple(self._manageable_inflight.values())
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _client_or_create(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10)
        return self._client

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        client, started = await self._client_or_create(), time.perf_counter()
        try:
            response = await client.request(method, f"{API_BASE}{path}", **kwargs)
            # Only safe reads may be retried. Never repeat a Discord mutation.
            if method == 'GET' and response.status_code == 429:
                delay = retry_after(response)
                if delay is not None and delay <= 2:
                    await asyncio.sleep(delay)
                    response = await client.request(method, f"{API_BASE}{path}", **kwargs)
            if response.is_error:
                logging.getLogger('tueka.discord').warning('Discord request failed', extra={'status': response.status_code})
            response.raise_for_status()
            return response
        finally:
            add_timing("discord_ms", (time.perf_counter() - started) * 1000)

    def _get_cached(self, kind: str, key: str) -> Any | None:
        entry = self._cache.get((kind, key))
        if entry and entry[0] > time.monotonic():
            return entry[1]
        self._cache.pop((kind, key), None)
        return None

    def _cache_for(self, kind: str, key: str, value: Any, seconds: int) -> Any:
        self._cache[(kind, key)] = (time.monotonic() + seconds, value)
        return value

    def invalidate_guild_resources(self, guild_id: int) -> None:
        self._cache.pop(("resources", str(guild_id)), None)

    async def exchange_code(self, code: str) -> dict[str, Any]:
        return (await self._request("POST", "/oauth2/token", data={"client_id": self.client_id, "client_secret": self.client_secret, "grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri})).json()

    async def user_guilds(self, access_token: str) -> list[dict[str, Any]]:
        return (await self._request("GET", "/users/@me/guilds", headers={"Authorization": f"Bearer {access_token}"})).json()

    async def current_user(self, access_token: str, *, use_cache: bool = True) -> dict[str, Any]:
        if use_cache and (cached := self._get_cached("user", access_token)) is not None:
            return cached
        value = (await self._request("GET", "/users/@me", headers={"Authorization": f"Bearer {access_token}"})).json()
        return self._cache_for("user", access_token, value, 300) if use_cache else value

    async def bot_user(self, *, use_cache: bool = True) -> dict[str, Any]:
        if use_cache and (cached := self._get_cached("bot_user", "self")) is not None:
            return cached
        value = (await self._request("GET", "/users/@me", headers={"Authorization": f"Bot {self.bot_token}"})).json()
        return self._cache_for("bot_user", "self", value, 6 * 60 * 60) if use_cache else value

    async def bot_guild_ids(self, *, use_cache: bool = True) -> set[int]:
        if use_cache and (cached := self._get_cached("bot_guilds", "self")) is not None:
            return cached
        response = await self._request("GET", "/users/@me/guilds", headers={"Authorization": f"Bot {self.bot_token}"})
        value = {int(guild["id"]) for guild in response.json()}
        return self._cache_for("bot_guilds", "self", value, 60) if use_cache else value

    async def guild_resources(self, guild_id: int, *, use_cache: bool = True) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
        key = str(guild_id)
        if use_cache and (cached := self._get_cached("resources", key)) is not None:
            return cached
        headers = {"Authorization": f"Bot {self.bot_token}"}
        channels, roles, bot_member = await asyncio.gather(
            self._request("GET", f"/guilds/{guild_id}/channels", headers=headers),
            self._request("GET", f"/guilds/{guild_id}/roles", headers=headers),
            self._request("GET", f"/guilds/{guild_id}/members/{self.client_id}", headers=headers),
        )
        all_roles = roles.json()
        bot_role_ids = {int(role_id) for role_id in bot_member.json().get("roles", [])}
        bot_top_position = max((int(role.get("position", 0)) for role in all_roles if int(role["id"]) in bot_role_ids), default=0)
        bot_permissions = 0
        for role in all_roles:
            if int(role["id"]) in bot_role_ids or role.get("name") == "@everyone":
                bot_permissions |= int(role.get("permissions", "0"))
        selectable_roles = [item for item in all_roles if item.get("name") != "@everyone" and not item.get("managed") and int(item.get("position", 0)) < bot_top_position and not (int(item.get("permissions", "0")) & MANAGEMENT_PERMISSIONS)]
        visible_channels = []
        for raw_channel in channels.json():
            if raw_channel.get("type") not in {0, 2, 4}:
                continue
            channel = dict(raw_channel)
            channel["bot_permissions"] = str(effective_channel_permissions(
                guild_id,
                int(self.client_id),
                bot_role_ids,
                bot_permissions,
                list(channel.get("permission_overwrites") or []),
            ))
            visible_channels.append(channel)
        value = (visible_channels, selectable_roles, bot_permissions)
        return self._cache_for("resources", key, value, 30) if use_cache else value

    async def guild_emojis(self, guild_id: int, *, use_cache: bool = True) -> list[dict[str, Any]]:
        key = str(guild_id)
        if use_cache and (cached := self._get_cached("emojis", key)) is not None:
            return cached
        value = (await self._request("GET", f"/guilds/{guild_id}/emojis", headers={"Authorization": f"Bot {self.bot_token}"})).json()
        result = [{"id": str(item["id"]), "name": str(item.get("name") or "emoji"), "animated": bool(item.get("animated"))} for item in value]
        return self._cache_for("emojis", key, result, 30) if use_cache else result

    async def channel_message(self, channel_id: int, message_id: int) -> dict[str, Any] | None:
        try:
            return (await self._request("GET", f"/channels/{channel_id}/messages/{message_id}", headers={"Authorization": f"Bot {self.bot_token}"})).json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    async def guild_member(self, guild_id: int, user_id: int, *, use_cache: bool = True) -> dict[str, Any] | None:
        key = f"{guild_id}:{user_id}"
        if use_cache and (cached := self._get_cached("guild_member", key)) is not None:
            return cached
        try:
            value = (await self._request("GET", f"/guilds/{guild_id}/members/{user_id}", headers={"Authorization": f"Bot {self.bot_token}"})).json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return self._cache_for("guild_member", key, value, 30) if use_cache else value

    async def publish_reaction_role_panel(self, channel_id: int, roles: list[dict[str, Any]], title: str, description: str) -> dict[str, Any]:
        components = [{"type": 1, "components": [{"type": 2, "style": 2, "label": role["name"][:80], "custom_id": f"tueka-rr:{role['id']}"} for role in roles[start:start + 5]]} for start in range(0, len(roles), 5)]
        payload = {"embeds": [{"title": title or "ロールを選択", "description": description or "ボタンでロールを付与・解除できます。"}], "components": components}
        return (await self._request("POST", f"/channels/{channel_id}/messages", headers={"Authorization": f"Bot {self.bot_token}"}, json=payload)).json()

    async def manageable_guilds(self, access_token: str, *, use_cache: bool = True) -> list[dict[str, Any]]:
        if use_cache and (cached := self._get_cached("manageable", access_token)) is not None:
            return cached
        if not use_cache:
            return await self._load_manageable_guilds(access_token, use_cache=False)
        task = self._manageable_inflight.get(access_token)
        if task is None:
            task = asyncio.create_task(self._load_manageable_guilds(access_token, use_cache=True))
            self._manageable_inflight[access_token] = task
            task.add_done_callback(lambda done: self._manageable_inflight.pop(access_token, None))
        # One disconnected HTTP reader must not cancel another reader's check.
        return await asyncio.shield(task)

    async def _load_manageable_guilds(self, access_token: str, *, use_cache: bool) -> list[dict[str, Any]]:
        user_guilds, bot_guilds = await asyncio.gather(self.user_guilds(access_token), self.bot_guild_ids(use_cache=use_cache))
        value = [guild for guild in user_guilds if int(guild["id"]) in bot_guilds and int(guild.get("permissions", "0")) & ADMINISTRATOR]
        # A live write authorization still refreshes the cache for the immediate
        # GET that follows it. Live writes never read this cache.
        return self._cache_for("manageable", access_token, value, 30)

    async def can_manage(self, access_token: str, guild_id: int, *, use_cache: bool = True) -> bool:
        return any(int(guild["id"]) == guild_id for guild in await self.manageable_guilds(access_token, use_cache=use_cache))
