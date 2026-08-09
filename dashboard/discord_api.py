"""Minimal Discord REST client used by the dashboard."""
from typing import Any

import httpx


API_BASE = "https://discord.com/api/v10"
ADMINISTRATOR = 0x8
MANAGEMENT_PERMISSIONS = 0x0000000000000008 | 0x0000000000000010 | 0x0000000000000020 | 0x0000000000000040 | 0x0000000000000080 | 0x0000000000000100 | 0x0000000000000400 | 0x0000000000001000 | 0x0000000000002000 | 0x0000000000004000 | 0x0000000000008000 | 0x0000000001000000 | 0x0000000020000000
PERMISSION_BITS = {"send_messages": 0x800, "manage_messages": 0x2000, "manage_channels": 0x10, "manage_roles": 0x10000000, "move_members": 0x1000000, "moderate_members": 0x10000000000, "kick_members": 0x2, "ban_members": 0x4}


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

    async def current_user(self, access_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{API_BASE}/users/@me", headers={"Authorization": f"Bearer {access_token}"})
            response.raise_for_status()
            return response.json()

    async def bot_user(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{API_BASE}/users/@me", headers={"Authorization": f"Bot {self.bot_token}"})
            response.raise_for_status()
            return response.json()

    async def bot_guild_ids(self) -> set[int]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{API_BASE}/users/@me/guilds", headers={"Authorization": f"Bot {self.bot_token}"})
            response.raise_for_status()
            return {int(guild["id"]) for guild in response.json()}

    async def guild_resources(self, guild_id: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
        headers = {"Authorization": f"Bot {self.bot_token}"}
        async with httpx.AsyncClient(timeout=10) as client:
            channels, roles, bot_member = await client.get(f"{API_BASE}/guilds/{guild_id}/channels", headers=headers), await client.get(f"{API_BASE}/guilds/{guild_id}/roles", headers=headers), await client.get(f"{API_BASE}/guilds/{guild_id}/members/@me", headers=headers)
            channels.raise_for_status()
            roles.raise_for_status()
            bot_member.raise_for_status()
        all_roles = roles.json()
        bot_role_ids = {int(role_id) for role_id in bot_member.json().get("roles", [])}
        bot_positions = [int(role.get("position", 0)) for role in all_roles if int(role["id"]) in bot_role_ids]
        bot_top_position = max(bot_positions, default=0)
        bot_permissions = 0
        for role in all_roles:
            if int(role["id"]) in bot_role_ids or role.get("name") == "@everyone":
                bot_permissions |= int(role.get("permissions", "0"))
        selectable_roles = [
            item for item in all_roles
            if item.get("name") != "@everyone" and not item.get("managed")
            and int(item.get("position", 0)) < bot_top_position
            and not (int(item.get("permissions", "0")) & MANAGEMENT_PERMISSIONS)
        ]
        return ([item for item in channels.json() if item.get("type") in {0, 2, 4}], selectable_roles, bot_permissions)

    async def publish_reaction_role_panel(self, channel_id: int, roles: list[dict[str, Any]], title: str, description: str) -> dict[str, Any]:
        components = [{"type": 1, "components": [{"type": 2, "style": 2, "label": role["name"][:80], "custom_id": f"tueka-rr:{role['id']}"} for role in roles[start:start + 5]]} for start in range(0, len(roles), 5)]
        payload = {"embeds": [{"title": title or "ロールを選択", "description": description or "ボタンでロールを付与・解除できます。"}], "components": components}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(f"{API_BASE}/channels/{channel_id}/messages", headers={"Authorization": f"Bot {self.bot_token}"}, json=payload)
            response.raise_for_status()
            return response.json()

    async def manageable_guilds(self, access_token: str) -> list[dict[str, Any]]:
        user_guilds, bot_guilds = await self.user_guilds(access_token), await self.bot_guild_ids()
        return [guild for guild in user_guilds if int(guild["id"]) in bot_guilds and int(guild.get("permissions", "0")) & ADMINISTRATOR]

    async def can_manage(self, access_token: str, guild_id: int) -> bool:
        return any(int(guild["id"]) == guild_id for guild in await self.manageable_guilds(access_token))
