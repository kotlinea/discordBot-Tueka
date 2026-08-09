"""Community automation: statistics voice channels, temporary voice, and tickets."""
import asyncio
import logging
from datetime import timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from storage import GuildStorage


LOGGER = logging.getLogger(__name__)


class CommunityCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.storage = GuildStorage(bot.settings.database_path)
        self.refresh_live_stats.start()

    def cog_unload(self) -> None:
        self.refresh_live_stats.cancel()

    async def _module_enabled(self, interaction: discord.Interaction, module_id: str) -> bool:
        if interaction.guild is None or not self.storage.module_enabled(interaction.guild.id, module_id):
            await interaction.response.send_message("この機能は管理者により無効です。", ephemeral=True)
            return False
        return True

    async def update_stats(self, guild: discord.Guild) -> None:
        settings = self.storage.get_module(guild.id, "live_stats")["settings"]
        channel_id = settings.get("stats_channel_id")
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, discord.VoiceChannel):
            return
        members = guild.member_count or len(guild.members)
        bots = sum(member.bot for member in guild.members)
        template = str(settings.get("stats_template") or "Members: {members} | Bots: {bots} | Roles: {roles}")[:90]
        try:
            name = template.format(members=members, bots=bots, humans=members - bots, roles=len(guild.roles))
        except (KeyError, ValueError):
            name = f"Members: {members} | Bots: {bots}"
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
        name = str(settings.get("temp_voice_name") or "{member}'s room").replace("{member}", member.display_name)[:100]
        try:
            channel = await guild.create_voice_channel(name=name, category=category, reason="Temporary voice channel")
            self.storage.add_temporary_voice_channel(channel.id, guild.id, member.id)
            await member.move_to(channel, reason="Temporary voice channel")
        except discord.HTTPException:
            LOGGER.warning("Could not create temporary voice channel", exc_info=True)

    async def _create_ticket(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None and isinstance(interaction.user, discord.Member)
        if not self.storage.module_enabled(interaction.guild.id, "tickets"):
            await interaction.response.send_message("この機能は管理者により無効です。", ephemeral=True)
            return
        settings = self.storage.get_module(interaction.guild.id, "tickets")["settings"]
        category = interaction.guild.get_channel(int(settings.get("ticket_category_id") or 0))
        staff_role = interaction.guild.get_role(int(settings.get("ticket_staff_role_id") or 0))
        if not isinstance(category, discord.CategoryChannel) or staff_role is None:
            await interaction.response.send_message("チケット設定が不完全です。", ephemeral=True)
            return
        existing = [channel for channel in category.text_channels if self.storage.ticket(channel.id) and self.storage.ticket(channel.id)["opener_id"] == interaction.user.id and self.storage.ticket(channel.id)["status"] == "open"]
        if existing:
            await interaction.response.send_message(f"すでに開いているチケットがあります: {existing[0].mention}", ephemeral=True)
            return
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True),
        }
        try:
            channel = await interaction.guild.create_text_channel(f"ticket-{interaction.user.name}"[:100], category=category, overwrites=overwrites, reason="Support ticket")
        except discord.HTTPException:
            await interaction.response.send_message("チケットを作成できませんでした。Botの権限を確認してください。", ephemeral=True)
            return
        self.storage.create_ticket(channel.id, interaction.guild.id, interaction.user.id)
        await channel.send(f"{interaction.user.mention} チケットを作成しました。スタッフが対応します。終了するには `/close_ticket` を使います。")
        await interaction.response.send_message(f"チケットを作成しました: {channel.mention}", ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type is discord.InteractionType.component and (interaction.data or {}).get("custom_id") == "tueka-ticket:create" and interaction.guild:
            await self._create_ticket(interaction)

    @app_commands.command(description="設定済みのサポートチケット用ボタンを投稿します。")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def publish_ticket_panel(self, interaction: discord.Interaction) -> None:
        if not await self._module_enabled(interaction, "tickets"):
            return
        assert interaction.guild is not None
        settings = self.storage.get_module(interaction.guild.id, "tickets")["settings"]
        channel = interaction.guild.get_channel(int(settings.get("ticket_panel_channel_id") or 0))
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("ダッシュボードでパネル投稿先を設定してください。", ephemeral=True)
            return
        embed = discord.Embed(title=str(settings.get("ticket_panel_title") or "サポートチケット"), description=str(settings.get("ticket_panel_description") or "サポートが必要な場合は、下のボタンを押してください。"))
        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="チケットを作成", style=discord.ButtonStyle.primary, custom_id="tueka-ticket:create"))
        try:
            await channel.send(embed=embed, view=view)
        except discord.HTTPException:
            await interaction.response.send_message("パネルを投稿できませんでした。Botの権限を確認してください。", ephemeral=True)
            return
        await interaction.response.send_message("サポートチケット用パネルを投稿しました。", ephemeral=True)

    @app_commands.command(description="このチケットを閉じ、議事録を保存します。")
    @app_commands.guild_only()
    async def close_ticket(self, interaction: discord.Interaction) -> None:
        if not await self._module_enabled(interaction, "tickets"):
            return
        assert interaction.guild is not None and isinstance(interaction.channel, discord.TextChannel)
        ticket = self.storage.ticket(interaction.channel.id)
        if not ticket or ticket["status"] != "open":
            await interaction.response.send_message("このチャンネルは開いているチケットではありません。", ephemeral=True)
            return
        staff_role_id = self.storage.get_module(interaction.guild.id, "tickets")["settings"].get("ticket_staff_role_id")
        is_staff = isinstance(interaction.user, discord.Member) and (interaction.user.guild_permissions.manage_channels or any(role.id == staff_role_id for role in interaction.user.roles))
        if interaction.user.id != ticket["opener_id"] and not is_staff:
            await interaction.response.send_message("チケット作成者またはスタッフだけが閉じられます。", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        messages = [message async for message in interaction.channel.history(limit=200, oldest_first=True)]
        transcript = [{"author_id": message.author.id, "author": str(message.author), "content": message.content, "created_at": message.created_at.replace(tzinfo=timezone.utc).isoformat()} for message in messages]
        self.storage.close_ticket(interaction.channel.id, interaction.user.id, transcript)
        log_id = self.storage.get_module(interaction.guild.id, "tickets")["settings"].get("ticket_log_channel_id")
        log = interaction.guild.get_channel(int(log_id)) if log_id else None
        if isinstance(log, discord.TextChannel):
            await log.send(f"チケット `{interaction.channel.name}` を {interaction.user.mention} が閉じました。議事録はSQLiteに保存済みです。")
        await interaction.followup.send("チケットを閉じました。チャンネルは5秒後に削除されます。", ephemeral=True)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason="Support ticket closed")
        except discord.HTTPException:
            LOGGER.warning("Could not delete closed ticket channel", exc_info=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommunityCog(bot))
