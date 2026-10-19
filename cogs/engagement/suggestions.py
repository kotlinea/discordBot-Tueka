"""Member suggestion intake, voting, and staff review."""
from __future__ import annotations

import logging
import os
import socket
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from guild_settings import GuildSettingsRepository
from jobs import run_batch
from suggestions.delivery import SuggestionDeliveryService
from suggestions.discord_adapter import DiscordSuggestionAdapter
from suggestions import SuggestionRepository, SuggestionService, normalize_settings


LOGGER = logging.getLogger("tueka.suggestions")
from suggestions.presentation import STATUS_LABELS, suggestion_embed, suggestion_view


class SuggestionModal(discord.ui.Modal):
    def __init__(self, cog: "SuggestionsCog", guild_id: int, settings: dict[str, Any]) -> None:
        super().__init__(title=settings["form_title"], timeout=600, custom_id=f"tueka-suggestion:submit:{guild_id}")
        self.cog, self.guild_id, self.settings = cog, guild_id, settings
        self.inputs: dict[str, discord.ui.TextInput] = {}
        for field in settings["form_fields"]:
            item = discord.ui.TextInput(
                label=field["label"], custom_id=field["key"], placeholder=field["placeholder"] or None,
                style=discord.TextStyle.paragraph if field["style"] == "paragraph" else discord.TextStyle.short,
                required=field["required"], min_length=field["min_length"] if field["min_length"] else None,
                max_length=field["max_length"],
            )
            self.inputs[field["key"]] = item
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.submit_modal(interaction, self.settings, {key: item.value for key, item in self.inputs.items()})

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        LOGGER.exception("Suggestion modal failed guild=%s", self.guild_id, exc_info=error)
        message = "提案を投稿できませんでした。Botの権限と投稿先を確認してください。"
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


class SuggestionReviewModal(discord.ui.Modal):
    def __init__(self, cog, item: dict, status: str):
        super().__init__(title='提案の審査理由', timeout=600)
        self.cog, self.item, self.status = cog, item, status
        self.reason = discord.ui.TextInput(label='理由', style=discord.TextStyle.paragraph, min_length=1, max_length=1000)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.guild.id != self.item['guild_id']:
            return
        module = self.cog.guild_settings.get_module(interaction.guild.id, 'suggestions')
        if not module['enabled'] or not self.cog._can_review(interaction, normalize_settings(module['settings'])):
            await interaction.response.send_message('現在この提案を審査する権限がありません。', ephemeral=True)
            return
        reason = self.reason.value.strip()
        if not reason:
            await interaction.response.send_message('審査理由を入力してください。', ephemeral=True)
            return
        try:
            self.cog.service.review(interaction.guild.id, self.item['id'], interaction.user.id, self.status,
                reason, expected_revision=self.item['revision'])
        except (LookupError, RuntimeError, ValueError):
            await interaction.response.send_message('提案が更新されています。再度開いて状態を確認してください。', ephemeral=True)
            return
        await interaction.response.send_message('審査を保存しました。投稿と通知の更新を待っています。', ephemeral=True)


class SuggestionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.guild_settings = GuildSettingsRepository(bot.settings.database_url)
        self.repository = SuggestionRepository(bot.settings.database_url)
        self.service = SuggestionService(self.repository)
        self.delivery = SuggestionDeliveryService(self.repository, self.guild_settings, DiscordSuggestionAdapter(bot))
        self.owner = f'suggestions:{socket.gethostname()}:{os.getpid()}'

    async def cog_load(self):
        self.deliver_outbox.start()

    def cog_unload(self):
        self.deliver_outbox.cancel()

    @tasks.loop(seconds=5)
    async def deliver_outbox(self):
        try:
            self.repository.purge_expired()
            await run_batch(self.repository.outbox_jobs, self.owner, self.delivery.deliver)
        except Exception as exc:
            LOGGER.error('Suggestion maintenance failed type=%s',type(exc).__name__)

    @deliver_outbox.before_loop
    async def before_outbox(self):
        await self.bot.wait_until_ready()

    def _settings(self, guild_id: int) -> dict[str, Any]:
        return normalize_settings(self.guild_settings.get_module(guild_id, "suggestions")["settings"])

    @app_commands.command(name="suggest", description="サーバーへアイデアや改善案を投稿します。")
    @app_commands.guild_only()
    async def suggest(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        module = self.guild_settings.get_module(interaction.guild.id, "suggestions")
        if not module["enabled"]:
            await interaction.response.send_message("Suggestionsは現在無効です。", ephemeral=True)
            return
        settings = normalize_settings(module["settings"])
        channel = interaction.guild.get_channel(settings["channel_id"]) if settings["channel_id"] else None
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("提案の投稿先が設定されていません。管理者へ連絡してください。", ephemeral=True)
            return
        await interaction.response.send_modal(SuggestionModal(self, interaction.guild.id, settings))

    async def submit_modal(self, interaction: discord.Interaction, settings: dict[str, Any], answers: dict[str, str]) -> None:
        if interaction.guild is None:
            return
        current = self.guild_settings.get_module(interaction.guild.id, "suggestions")
        if not current["enabled"]:
            await interaction.response.send_message("Suggestionsは現在無効です。", ephemeral=True)
            return
        settings = normalize_settings(current["settings"])
        channel = interaction.guild.get_channel(settings["channel_id"]) if settings["channel_id"] else None
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("提案の投稿先を利用できません。", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        item = self.service.submit(interaction.guild.id, channel.id, interaction.user.id, settings, answers)
        await run_batch(self.repository.outbox_jobs, self.owner, self.delivery.deliver)
        item = self.repository.get(interaction.guild.id, item['id'])
        if item['status'] == 'delivery_failed':
            await interaction.followup.send("提案を投稿できませんでした。管理者へ通知してください。", ephemeral=True)
        elif item.get('message_id'):
            await interaction.followup.send(f"提案 #{item['id']} を投稿しました。", ephemeral=True)
        else:
            await interaction.followup.send(f"提案 #{item['id']} を受け付けました。投稿を待っています。", ephemeral=True)

    @staticmethod
    def _can_review(interaction: discord.Interaction, settings: dict[str, Any]) -> bool:
        member = interaction.user
        if not isinstance(member, discord.Member):
            return False
        if member.guild_permissions.manage_messages:
            return True
        allowed = set(settings.get("review_role_ids") or [])
        return any(role.id in allowed for role in member.roles)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type is not discord.InteractionType.component or interaction.guild is None or interaction.message is None:
            return
        custom_id = (interaction.data or {}).get("custom_id", "")
        if not isinstance(custom_id, str) or not custom_id.startswith("tueka-suggestion:"):
            return
        try:
            _, action, raw_id, value = custom_id.split(":")
            suggestion_id = int(raw_id)
        except (TypeError, ValueError):
            return
        module = self.guild_settings.get_module(interaction.guild.id, "suggestions")
        if not module["enabled"]:
            await interaction.response.send_message("Suggestionsは現在無効です。", ephemeral=True)
            return
        settings = normalize_settings(module["settings"])
        item = self.repository.get(interaction.guild.id, suggestion_id)
        if item is None or item.get("message_id") != interaction.message.id:
            await interaction.response.send_message("この提案は現在操作できません。", ephemeral=True)
            return
        try:
            if action == "vote":
                item = self.service.vote(interaction.guild.id, suggestion_id, interaction.user.id, 1 if value == "up" else -1, settings)
            elif action == "review":
                if not self._can_review(interaction, settings):
                    await interaction.response.send_message("この提案を審査する権限がありません。", ephemeral=True)
                    return
                if value not in {'reviewing', 'approved', 'rejected', 'implemented'}:
                    return
                await interaction.response.send_modal(SuggestionReviewModal(self, item, value))
                return
            else:
                return
        except PermissionError:
            await interaction.response.send_message("投票は無効です。", ephemeral=True)
            return
        except RuntimeError:
            message = "この提案の審査はすでに完了しています。" if action == "review" else "審査が完了した提案には投票できません。"
            await interaction.response.send_message(message, ephemeral=True)
            return
        await interaction.response.edit_message(embed=suggestion_embed(item, settings), view=suggestion_view(item, settings))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SuggestionsCog(bot))
