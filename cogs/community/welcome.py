"""Configurable welcome and leave messages; default roles stay in autorole."""
import re

import discord
from discord import app_commands
from discord.ext import commands

from guild_settings import GuildSettingsRepository


TOKEN_RE = re.compile(r"\{([^{}]+)\}")
VARIABLE_HELP = "{user}, {username}, {displayname}, {server}, {membercount}"


class WelcomeCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.guild_settings = GuildSettingsRepository(bot.settings.database_url)

    @staticmethod
    def render_content(template: str, member: discord.Member) -> str:
        values = {
            "user": member.mention,
            "username": discord.utils.escape_markdown(member.name),
            "displayname": discord.utils.escape_markdown(member.display_name),
            "server": discord.utils.escape_markdown(member.guild.name),
            "membercount": str(member.guild.member_count or len(member.guild.members)),
        }

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            return values[name] if name in values else f"\\{{{name}\\}}"

        return TOKEN_RE.sub(replace, template)

    async def _send_configured_message(self, member: discord.Member, event: str) -> None:
        module = self.guild_settings.get_module(member.guild.id, "welcome")
        settings = module["settings"]
        if not module["enabled"] or not settings.get(f"{event}_enabled"):
            return
        channel_id = settings.get(f"{event}_channel_id")
        content = str(settings.get(f"{event}_content") or "")
        channel = member.guild.get_channel(int(channel_id)) if channel_id else None
        if not content or not isinstance(channel, discord.TextChannel):
            return
        rendered = self.render_content(content, member)
        mentions = discord.AllowedMentions(everyone=False, roles=False, users=[member], replied_user=False)
        if settings.get(f"{event}_format") == "embed":
            title, color = ("Welcome", discord.Color.green()) if event == "welcome" else ("Goodbye", discord.Color.orange())
            await channel.send(embed=discord.Embed(title=title, description=rendered[:4096], color=color), allowed_mentions=mentions)
        else:
            await channel.send(rendered[:2000], allowed_mentions=mentions)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self._send_configured_message(member, "welcome")
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await self._send_configured_message(member, "leave")

    @app_commands.command(description="ウェルカムメッセージを送信します。")
    @app_commands.guild_only()
    async def welcome(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        if interaction.guild and not self.guild_settings.module_enabled(interaction.guild.id, "welcome"):
            await interaction.response.send_message("この機能は管理者により無効です。", ephemeral=True)
            return
        member = member or interaction.user
        await interaction.response.send_message(f"{member.mention}さん、ようこそ! 🎉")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WelcomeCog(bot))
