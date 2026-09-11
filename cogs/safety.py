"""Guild-scoped safety modules: moderation, filtering and spam."""
import logging
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from storage import GuildStorage
from automod.service import ModerationService


MAX_TIMEOUT = 28 * 24 * 60
LOGGER = logging.getLogger(__name__)


class SafetyCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot, self.storage = bot, GuildStorage(bot.settings.database_path)
        self.moderation = ModerationService(bot, self.storage)

    async def _enabled(self, interaction: discord.Interaction, module_id: str) -> bool:
        if interaction.guild is None or not self.storage.module_enabled(interaction.guild.id, module_id):
            await interaction.response.send_message("この機能は管理者により無効です。", ephemeral=True)
            return False
        return True

    async def _dm(self, member: discord.Member, text: str) -> bool:
        try:
            await member.send(text)
            return True
        except discord.HTTPException:
            return False

    async def _audit(self, guild: discord.Guild, text: str) -> None:
        module = self.storage.get_module(guild.id, "audit_log")
        channel_id = module["settings"].get("management_channel_id")
        if not module["enabled"] or not channel_id:
            return
        channel = guild.get_channel(int(channel_id))
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(text, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                LOGGER.warning("Could not write moderation audit log", exc_info=True)

    @staticmethod
    def _manageable(actor: discord.Member, target: discord.Member, action: str) -> str | None:
        return ModerationService.manageable(actor, target, action)

    async def _apply_case(self, guild: discord.Guild, member: discord.Member, action: str, reason: str | None, moderator_id: int | None, minutes: int = 0, notify: bool = True) -> None:
        await self.moderation.apply_case(guild, member, action, reason, moderator_id, minutes, notify)

    async def _warn(self, guild: discord.Guild, member: discord.Member, reason: str | None, moderator_id: int | None) -> int:
        return await self.moderation.warn(guild, member, reason, moderator_id)

    @app_commands.command(description="メンバーに警告を与えます。")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None):
        if not await self._enabled(interaction, "moderation"):
            return
        assert interaction.guild is not None
        error = self._manageable(interaction.user, member, "timeout")
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        count = await self._warn(interaction.guild, member, reason, interaction.user.id)
        await interaction.response.send_message(f"{member.mention} に警告しました（現在 {count} 回）。", ephemeral=True)

    @app_commands.command(description="メンバーを一時的にタイムアウトします。")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str | None = None):
        if not await self._enabled(interaction, "moderation"):
            return
        assert interaction.guild is not None
        error = self._manageable(interaction.user, member, "timeout")
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        try:
            await self._apply_case(interaction.guild, member, "timeout", reason, interaction.user.id, minutes, True)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message("タイムアウトしました。", ephemeral=True)

    @app_commands.command(description="メンバーをキックします。")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.guild_only()
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None):
        if not await self._enabled(interaction, "moderation"):
            return
        assert interaction.guild is not None
        error = self._manageable(interaction.user, member, "kick")
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        await self._apply_case(interaction.guild, member, "kick", reason, interaction.user.id)
        await interaction.response.send_message("キックしました。", ephemeral=True)

    @app_commands.command(description="メンバーを追放します。")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.guild_only()
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None):
        if not await self._enabled(interaction, "moderation"):
            return
        assert interaction.guild is not None
        error = self._manageable(interaction.user, member, "ban")
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        await self._apply_case(interaction.guild, member, "ban", reason, interaction.user.id)
        await interaction.response.send_message("追放しました。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SafetyCog(bot))
