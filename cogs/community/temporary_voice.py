"""Community automation: statistics voice channels and temporary voice."""
import logging

import discord
from discord.ext import commands

from community import CommunityRepository
from guild_settings import GuildSettingsRepository
from template_defaults import TEMP_VOICE_NAME_DEFAULT


LOGGER = logging.getLogger(__name__)


class TemporaryVoiceCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repository = CommunityRepository(bot.settings.database_url)
        self.guild_settings = GuildSettingsRepository(bot.settings.database_url)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        guild = member.guild
        if not self.guild_settings.module_enabled(guild.id, "temporary_voice"):
            return
        if before.channel and self.repository.temporary_voice_channel(before.channel.id) and not before.channel.members:
            try:
                await before.channel.delete(reason="Temporary voice channel became empty")
            except discord.HTTPException:
                LOGGER.warning("Could not delete temporary voice channel", exc_info=True)
            self.repository.remove_temporary_voice_channel(before.channel.id)
        settings = self.guild_settings.get_module(guild.id, "temporary_voice")["settings"]
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
            self.repository.add_temporary_voice_channel(channel.id, guild.id, member.id)
            await member.move_to(channel, reason="Temporary voice channel")
        except discord.HTTPException:
            LOGGER.warning("Could not create temporary voice channel", exc_info=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TemporaryVoiceCog(bot))
