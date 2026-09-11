"""Community automation: statistics voice channels and temporary voice."""
import logging

import discord
from discord.ext import commands, tasks

from storage import GuildStorage
from template_defaults import STATS_TEMPLATE_DEFAULT, TEMP_VOICE_NAME_DEFAULT


LOGGER = logging.getLogger(__name__)


class CommunityCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.storage = GuildStorage(bot.settings.database_path)
        self.refresh_live_stats.start()

    def cog_unload(self) -> None:
        self.refresh_live_stats.cancel()


    async def update_stats(self, guild: discord.Guild) -> None:
        settings = self.storage.get_module(guild.id, "live_stats")["settings"]
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
        for guild_id in self.storage.enabled_module_guild_ids("live_stats"):
            guild = self.bot.get_guild(guild_id)
            if guild:
                await self.update_stats(guild)

    @refresh_live_stats.before_loop
    async def before_refresh_live_stats(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if self.storage.module_enabled(member.guild.id, "live_stats"):
            await self.update_stats(member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if self.storage.module_enabled(member.guild.id, "live_stats"):
            await self.update_stats(member.guild)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.roles != after.roles and self.storage.module_enabled(after.guild.id, "live_stats"):
            await self.update_stats(after.guild)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        guild = member.guild
        if self.storage.module_enabled(guild.id, "live_stats"):
            await self.update_stats(guild)
        if not self.storage.module_enabled(guild.id, "temporary_voice"):
            return
        if before.channel and self.storage.temporary_voice_channel(before.channel.id) and not before.channel.members:
            try:
                await before.channel.delete(reason="Temporary voice channel became empty")
            except discord.HTTPException:
                LOGGER.warning("Could not delete temporary voice channel", exc_info=True)
            self.storage.remove_temporary_voice_channel(before.channel.id)
        settings = self.storage.get_module(guild.id, "temporary_voice")["settings"]
        trigger_id = settings.get("temp_voice_trigger_id")
        if not after.channel or not trigger_id or after.channel.id != int(trigger_id):
            return
        category_id = settings.get("temp_voice_category_id")
        category = guild.get_channel(int(category_id)) if category_id else None
        if category is not None and not isinstance(category, discord.CategoryChannel):
            category = None
        name = str(settings.get("temp_voice_name") or TEMP_VOICE_NAME_DEFAULT).replace("{member}", member.display_name)[:100]
        try:
            channel = await guild.create_voice_channel(name=name, category=category, reason="Temporary voice channel")
            self.storage.add_temporary_voice_channel(channel.id, guild.id, member.id)
            await member.move_to(channel, reason="Temporary voice channel")
        except discord.HTTPException:
            LOGGER.warning("Could not create temporary voice channel", exc_info=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommunityCog(bot))
