"""Guild-scoped safety modules: moderation, filtering and spam."""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from moderation import ModerationRepository
from guild_settings import GuildSettingsRepository
from moderation.discord_adapter import DiscordModerationAdapter, action_context, guild_ref, member_ref
from moderation.contracts import ActionFailure
from moderation.service import ModerationService


MAX_TIMEOUT = 28 * 24 * 60
LOGGER = logging.getLogger(__name__)


class SafetyCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot, self.moderation_repository = bot, ModerationRepository(bot.settings.database_url)
        self.guild_settings = GuildSettingsRepository(bot.settings.database_url)
        self.moderation = ModerationService(DiscordModerationAdapter(bot), self.moderation_repository, self.guild_settings)

    async def _enabled(self, interaction: discord.Interaction, module_id: str) -> bool:
        if interaction.guild is None or not self.guild_settings.module_enabled(interaction.guild.id, module_id):
            await interaction.response.send_message("この機能は管理者により無効です。", ephemeral=True)
            return False
        return True

    def _manageable(self, actor: discord.Member, target: discord.Member, action: str) -> str | None:
        return self.moderation.manageable(member_ref(actor), member_ref(target), action)

    async def _apply_case(self, guild: discord.Guild, member: discord.Member, action: str, reason: str | None, moderator_id: int | None, minutes: int = 0, notify: bool = True) -> None:
        await self.moderation.apply_case(guild_ref(guild), member_ref(member), action, reason, moderator_id, minutes, notify)

    async def _warn(self, guild: discord.Guild, member: discord.Member, reason: str | None, moderator_id: int | None, execution_key: str | None = None) -> int:
        return await self.moderation.warn(guild_ref(guild), member_ref(member), reason, moderator_id, execution_key=execution_key)

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
        count = await self._warn(interaction.guild, member, reason, interaction.user.id, str(interaction.id))
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
