"""Community automation: statistics voice channels and temporary voice."""
import logging

import discord
from discord.ext import commands, tasks

from guild_settings import GuildSettingsRepository
from template_defaults import STATS_TEMPLATE_DEFAULT


LOGGER = logging.getLogger(__name__)


class LiveStatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.guild_settings = GuildSettingsRepository(bot.settings.database_url)
        self.refresh_live_stats.start()

    def cog_unload(self) -> None:
        self.refresh_live_stats.cancel()


    async def update_stats(self, guild: discord.Guild) -> None:
        settings = self.guild_settings.get_module(guild.id, "live_stats")["settings"]
        channel_id = settings.get("stats_channel_id")
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, discord.VoiceChannel):
            return
        members = guild.member_count or len(guild.members)
        bots = sum(member.bot for member in guild.members)
        template = str(settings.get("stats_template") or STATS_TEMPLATE_DEFAULT)[:90]
        try:
            name = template.format(members=members, bots=bots, humans=members - bots, roles=len(guild.roles))
        except (KeyError, ValueError):
            name = STATS_TEMPLATE_DEFAULT.format(members=members, bots=bots, humans=members - bots, roles=len(guild.roles))
        if channel.name != name:
            try:
                await channel.edit(name=name[:100], reason="Live statistics update")
            except discord.HTTPException:
                LOGGER.warning("Failed to update live statistics in guild %s", guild.id, exc_info=True)

    @tasks.loop(minutes=5)
    async def refresh_live_stats(self) -> None:
        for guild_id in self.guild_settings.enabled_module_guild_ids("live_stats"):
            guild = self.bot.get_guild(guild_id)
            if guild:
                await self.update_stats(guild)

    @refresh_live_stats.before_loop
    async def before_refresh_live_stats(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if self.guild_settings.module_enabled(member.guild.id, "live_stats"):
            await self.update_stats(member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if self.guild_settings.module_enabled(member.guild.id, "live_stats"):
            await self.update_stats(member.guild)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.roles != after.roles and self.guild_settings.module_enabled(after.guild.id, "live_stats"):
            await self.update_stats(after.guild)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        guild = member.guild
        if self.guild_settings.module_enabled(guild.id, "live_stats"):
            await self.update_stats(guild)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LiveStatsCog(bot))
