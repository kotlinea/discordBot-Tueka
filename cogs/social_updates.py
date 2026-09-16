"""Deliver normalized social-provider events stored by polling and webhooks."""
import os
import re
import socket

from jobs import Outcome, run_batch

from discord.ext import commands, tasks

from social import SocialRepository
from social.service import SocialDeliveryService
from social.discord_adapter import DiscordSocialAdapter
from guild_settings import GuildSettingsRepository
from social.models import render_template


MODULE_FOR_PROVIDER = {"youtube": "youtube_updates", "twitch": "twitch_updates", "tiktok": "tiktok_updates", "x": "x_updates", "instagram": "instagram_updates"}


class SocialUpdatesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.social_repository = SocialRepository(bot.settings.database_path)
        self.guild_settings = GuildSettingsRepository(bot.settings.database_path)
        self.delivery = SocialDeliveryService(self.social_repository, self.guild_settings, DiscordSocialAdapter(bot))
        self.owner = f"discord:{socket.gethostname()}:{os.getpid()}"
        self.deliver_events.start()

    def cog_unload(self) -> None:
        self.deliver_events.cancel()

    @staticmethod
    def render_template(template: str, payload: dict) -> str:
        values = {**payload, "event": payload.get("event") or payload.get("type", ""), "type": payload.get("type", "")}
        rendered = render_template(template, values, limit=1900)
        return re.sub(r"\{type\}", str(values["type"]), rendered)[:1900]


    async def _deliver(self, event: dict) -> bool:
        return await self.delivery.deliver(event)

    @tasks.loop(seconds=5)
    async def deliver_events(self) -> None:
        await run_batch(self.social_repository.event_jobs, self.owner, self._deliver_event, limit=10, lease_seconds=120)

    async def _deliver_event(self, event: dict) -> Outcome:
        if await self._deliver(event):
            return Outcome()
        return Outcome('One or more Discord deliveries need retry', retry=True)

    @deliver_events.before_loop
    async def before_deliver_events(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SocialUpdatesCog(bot))
