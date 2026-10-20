"""Unified /mod command group backed by the shared Moderation Service."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from moderation.discord_adapter import DiscordModerationAdapter, action_context, guild_ref, member_ref
from moderation.contracts import ActionFailure, MemberRef
from moderation.service import ActionContext, ModerationService
from moderation import ModerationRepository
from guild_settings import GuildSettingsRepository


class ModerationCommandsCog(commands.Cog):
    help_category = 'モデレーション'
    help_module = 'moderation'

    mod = app_commands.Group(name="mod", description="モデレーション操作")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.moderation_repository = ModerationRepository(bot.settings.database_url)
        self.guild_settings = GuildSettingsRepository(bot.settings.database_url)
        self.service = ModerationService(DiscordModerationAdapter(bot), self.moderation_repository, self.guild_settings)

    async def _enabled(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not self.guild_settings.module_enabled(interaction.guild.id, "moderation"):
            await interaction.response.send_message("Moderationは無効です。", ephemeral=True)
            return False
        return True

    async def _member_action(self, interaction: discord.Interaction, member: discord.Member, action: str,
            reason: str | None, duration_minutes: int = 0) -> None:
        if not await self._enabled(interaction):
            return
        assert interaction.guild is not None and isinstance(interaction.user, discord.Member)
        try:
            case_id = await self.service.apply_case(guild_ref(interaction.guild), member_ref(member), action, reason, interaction.user.id,
                duration_minutes, True, source="manual", actor=member_ref(interaction.user), execution_key=str(interaction.id))
        except (ValueError, PermissionError, ActionFailure, discord.Forbidden, discord.HTTPException) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(f"{action}を実行しました。Case #{case_id}", ephemeral=True)

    @mod.command(name="warn", description="Warningを追加します。")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mod_warn(self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None) -> None:
        if not await self._enabled(interaction):
            return
        assert interaction.guild is not None and isinstance(interaction.user, discord.Member)
        try:
            count = await self.service.warn(guild_ref(interaction.guild), member_ref(member), reason, interaction.user.id,
                actor=member_ref(interaction.user), execution_key=str(interaction.id))
        except PermissionError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(f"Warningを追加しました（累計{count}回）。", ephemeral=True)

    @mod.command(name="timeout", description="Timeoutを設定します。")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mod_timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int,1,40320], reason: str | None = None) -> None:
        await self._member_action(interaction, member, "timeout", reason, minutes)

    @mod.command(name="untimeout", description="Timeoutを解除します。")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mod_untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None) -> None:
        await self._member_action(interaction, member, "untimeout", reason)

    @mod.command(name="kick", description="メンバーをKickします。")
    @app_commands.checks.has_permissions(kick_members=True)
    async def mod_kick(self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None) -> None:
        await self._member_action(interaction, member, "kick", reason)

    @mod.command(name="ban", description="メンバーをBanします。")
    @app_commands.checks.has_permissions(ban_members=True)
    async def mod_ban(self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None) -> None:
        await self._member_action(interaction, member, "ban", reason)

    @mod.command(name="softban", description="メンバーをSoftbanします。")
    @app_commands.checks.has_permissions(ban_members=True)
    async def mod_softban(self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None) -> None:
        await self._member_action(interaction, member, "softban", reason)

    @mod.command(name="unban", description="ユーザーIDを指定してBanを解除します。")
    @app_commands.checks.has_permissions(ban_members=True)
    async def mod_unban(self, interaction: discord.Interaction, user_id: str, reason: str | None = None) -> None:
        if not await self._enabled(interaction):
            return
        assert interaction.guild is not None
        try:
            target_id = int(user_id)
            case_id = await self.service.apply_case(guild_ref(interaction.guild), MemberRef(target_id, interaction.guild.id, str(target_id)),
                'unban', reason, interaction.user.id, notify=False, execution_key=str(interaction.id),
                actor=member_ref(interaction.user))
        except (ValueError, PermissionError, ActionFailure) as exc:
            await interaction.response.send_message(f"Banを解除できません: {exc}",ephemeral=True)
            return
        await interaction.response.send_message(f"Banを解除しました。Case #{case_id}",ephemeral=True)

    async def _channel_action(self, interaction: discord.Interaction, action: str, channel: discord.TextChannel | None,
            reason: str | None, *, count: int = 10, duration: int = 30) -> None:
        if not await self._enabled(interaction):
            return
        assert interaction.guild is not None
        event_id = self.moderation_repository.create_moderation_event(interaction.guild.id,family="infraction",event_type="infraction_change",
            source="manual",reason=reason or action,actor_id=interaction.user.id,target_user_id=None,
            channel_id=channel.id if channel else None,dedupe_key=f"interaction:{interaction.id}")
        if event_id is None:
            await interaction.response.send_message("この操作はすでに処理されています。",ephemeral=True)
            return
        value = {"type":action}
        if action == "purge": value["count"] = count
        if action == "lockdown": value["duration_minutes"] = duration
        results = await self.service.execute_actions(action_context(interaction.guild,channel=channel,actor=interaction.user),
            {"family":"infraction","name":"Manual action","mode":"enforce","actions":[value]},reason or action,event_id,{})
        self.moderation_repository.finish_moderation_event(event_id,results)
        await interaction.response.send_message(f"処理結果: {results[0]['status']} · Event #{event_id}",ephemeral=True)

    @mod.command(name="purge", description="最近のメッセージを削除します。")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def mod_purge(self, interaction: discord.Interaction, count: app_commands.Range[int,1,100], reason: str | None = None) -> None:
        await self._channel_action(interaction,"purge",interaction.channel if isinstance(interaction.channel,discord.TextChannel) else None,reason,count=count)

    @mod.command(name="lock", description="チャンネルをロックします。")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def mod_lock(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None, reason: str | None = None) -> None:
        await self._channel_action(interaction,"lock",channel or (interaction.channel if isinstance(interaction.channel,discord.TextChannel) else None),reason)

    @mod.command(name="unlock", description="チャンネルのロックを解除します。")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def mod_unlock(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None, reason: str | None = None) -> None:
        await self._channel_action(interaction,"unlock",channel or (interaction.channel if isinstance(interaction.channel,discord.TextChannel) else None),reason)

    @mod.command(name="lockdown", description="サーバーを期限付きでLockdownします。")
    @app_commands.checks.has_permissions(administrator=True)
    async def mod_lockdown(self, interaction: discord.Interaction, minutes: app_commands.Range[int,1,1440] = 30, reason: str | None = None) -> None:
        await self._channel_action(interaction,"lockdown",None,reason,duration=minutes)

    @mod.command(name="unlockdown", description="有効なLockdownを解除します。")
    @app_commands.checks.has_permissions(administrator=True)
    async def mod_unlockdown(self, interaction: discord.Interaction, reason: str | None = None) -> None:
        await self._channel_action(interaction,"unlockdown",None,reason)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationCommandsCog(bot))
