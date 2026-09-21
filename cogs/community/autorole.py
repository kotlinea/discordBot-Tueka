"""Assign the configured join role independently of welcome delivery."""
import discord
from discord.ext import commands
from guild_settings import GuildSettingsRepository


class AutoroleCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.guild_settings = GuildSettingsRepository(bot.settings.database_url)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        module = self.guild_settings.get_module(member.guild.id, 'autorole')
        role_id = module['settings'].get('default_role_id') if module['enabled'] else None
        role = member.guild.get_role(role_id) if role_id else None
        if role:
            try:
                await member.add_roles(role, reason='Default role on join')
            except discord.Forbidden:
                pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoroleCog(bot))
