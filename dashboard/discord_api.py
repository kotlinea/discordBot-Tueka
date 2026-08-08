"""Minimal Discord REST client used by the dashboard."""
from typing import Any

import httpx


API_BASE = "https://discord.com/api/v10"
ADMINISTRATOR = 0x8


class DiscordAPI:
    def __init__(self, bot_token: str, client_id: str, client_secret: str, redirect_uri: str) -> None:
        self.bot_token = bot_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    async def exchange_code(self, code: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(f"{API_BASE}/oauth2/token", data={"client_id": self.client_id, "client_secret": self.client_secret, "grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri})
            response.raise_for_status()
            return response.json()

    async def user_guilds(self, access_token: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{API_BASE}/users/@me/guilds", headers={"Authorization": f"Bearer {access_token}"})
            response.raise_for_status()
            return response.json()

    async def bot_guild_ids(self) -> set[int]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{API_BASE}/users/@me/guilds", headers={"Authorization": f"Bot {self.bot_token}"})
            response.raise_for_status()
            return {int(guild["id"]) for guild in response.json()}

    async def guild_resources(self, guild_id: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        headers = {"Authorization": f"Bot {self.bot_token}"}
        async with httpx.AsyncClient(timeout=10) as client:
            channels, roles = await client.get(f"{API_BASE}/guilds/{guild_id}/channels", headers=headers), await client.get(f"{API_BASE}/guilds/{guild_id}/roles", headers=headers)
            channels.raise_for_status()
            roles.raise_for_status()
        return ([item for item in channels.json() if item.get("type") == 0], [item for item in roles.json() if item.get("name") != "@everyone"])

    async def manageable_guilds(self, access_token: str) -> list[dict[str, Any]]:
        user_guilds, bot_guilds = await self.user_guilds(access_token), await self.bot_guild_ids()
        return [guild for guild in user_guilds if int(guild["id"]) in bot_guilds and int(guild.get("permissions", "0")) & ADMINISTRATOR]

    async def can_manage(self, access_token: str, guild_id: int) -> bool:
        return any(int(guild["id"]) == guild_id for guild in await self.manageable_guilds(access_token))
