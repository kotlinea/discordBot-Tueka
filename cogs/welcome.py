import discord
from discord import app_commands
from discord.ext import commands
from storage import GuildStorage


class WelcomeCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.storage = GuildStorage(bot.settings.database_path)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        module = self.storage.get_module(member.guild.id, "welcome")
        if not module["enabled"]:
            return
        channel_id = module["settings"].get("welcome_channel_id")
        channel = member.guild.get_channel(channel_id) if channel_id else None
        if isinstance(channel, discord.abc.Messageable):
            await channel.send(f"{member.mention}さん、**{member.guild.name}**へようこそ! 🎉")
        role_id = module["settings"].get("default_role_id")
        role = member.guild.get_role(role_id) if role_id else None
        if role:
            try:
                await member.add_roles(role, reason="Default role on join")
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        module = self.storage.get_module(member.guild.id, "welcome")
        if not module["enabled"]:
            return
        channel_id = module["settings"].get("welcome_channel_id")
        channel = member.guild.get_channel(channel_id) if channel_id else None
        if isinstance(channel, discord.abc.Messageable):
            await channel.send(f"Goodbye {member.name}! We'll miss you! 😢")

    @app_commands.command(description="ウェルカムメッセージを送信します。")
    @app_commands.guild_only()
    async def welcome(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        if interaction.guild and not self.storage.module_enabled(interaction.guild.id, "welcome"):
            await interaction.response.send_message("この機能は管理者により無効です。", ephemeral=True)
            return
        member = member or interaction.user
        await interaction.response.send_message(f"{member.mention}さん、ようこそ! 🎉")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WelcomeCog(bot))
