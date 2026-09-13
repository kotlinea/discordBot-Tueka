"""Member suggestion intake, voting, and staff review."""
from __future__ import annotations

import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from guild_settings import GuildSettingsRepository
from suggestions import SuggestionRepository, SuggestionService, normalize_settings


LOGGER = logging.getLogger("tueka.suggestions")
STATUS_LABELS = {
    "pending": "審査待ち",
    "reviewing": "審査中",
    "approved": "承認済み",
    "rejected": "却下",
    "delivery_failed": "投稿失敗",
}
STATUS_COLORS = {
    "pending": 0x64748B,
    "reviewing": 0xD97706,
    "approved": 0x15803D,
    "rejected": 0xB91C1C,
    "delivery_failed": 0xB91C1C,
}


def suggestion_embed(item: dict[str, Any], settings: dict[str, Any]) -> discord.Embed:
    status = str(item["status"])
    embed = discord.Embed(
        title=f"提案 #{item['id']} · {STATUS_LABELS.get(status, status)}",
        color=STATUS_COLORS.get(status, STATUS_COLORS["pending"]),
    )
    fields_by_key = {field["key"]: field for field in normalize_settings(settings)["form_fields"]}
    for key, value in item["answers"].items():
        if not value:
            continue
        label = fields_by_key.get(key, {}).get("label", key)
        embed.add_field(name=str(label)[:256], value=str(value)[:1024], inline=False)
    if settings.get("show_author", True):
        embed.set_author(name=f"投稿者: {item['author_id']}")
    reviewer = f" · 担当 <@{item['reviewer_id']}>" if item.get("reviewer_id") else ""
    embed.set_footer(text=f"賛成 {item.get('upvotes', 0)} · 反対 {item.get('downvotes', 0)}{reviewer}")
    return embed


def suggestion_view(item: dict[str, Any], settings: dict[str, Any]) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    closed = item["status"] in {"approved", "rejected", "delivery_failed"}
    if settings.get("allow_voting", True):
        view.add_item(discord.ui.Button(
            label=f"賛成 {item.get('upvotes', 0)}", emoji="👍", style=discord.ButtonStyle.secondary,
            custom_id=f"tueka-suggestion:vote:{item['id']}:up", disabled=closed,
        ))
        view.add_item(discord.ui.Button(
            label=f"反対 {item.get('downvotes', 0)}", emoji="👎", style=discord.ButtonStyle.secondary,
            custom_id=f"tueka-suggestion:vote:{item['id']}:down", disabled=closed,
        ))
    view.add_item(discord.ui.Button(
        label="審査中", style=discord.ButtonStyle.secondary,
        custom_id=f"tueka-suggestion:review:{item['id']}:reviewing", disabled=closed or item["status"] == "reviewing",
    ))
    view.add_item(discord.ui.Button(
        label="承認", style=discord.ButtonStyle.success,
        custom_id=f"tueka-suggestion:review:{item['id']}:approved", disabled=closed,
    ))
    view.add_item(discord.ui.Button(
        label="却下", style=discord.ButtonStyle.danger,
        custom_id=f"tueka-suggestion:review:{item['id']}:rejected", disabled=closed,
    ))
    return view


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


class SuggestionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.guild_settings = GuildSettingsRepository(bot.settings.database_path)
        self.repository = SuggestionRepository(bot.settings.database_path)
        self.service = SuggestionService(self.repository)

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
        try:
            message = await channel.send(
                embed=suggestion_embed(item, settings), view=suggestion_view(item, settings),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            item = self.repository.attach_message(interaction.guild.id, item["id"], message.id)
        except discord.HTTPException as exc:
            self.repository.mark_delivery_failed(interaction.guild.id, item["id"], type(exc).__name__)
            await interaction.followup.send("提案を投稿できませんでした。管理者へ通知してください。", ephemeral=True)
            return
        await interaction.followup.send(f"提案 #{item['id']} を投稿しました。", ephemeral=True)

    @staticmethod
    def _can_review(interaction: discord.Interaction, settings: dict[str, Any]) -> bool:
        member = interaction.user
        if not isinstance(member, discord.Member):
            return False
        if member.guild_permissions.manage_messages:
            return True
        allowed = set(settings.get("review_role_ids") or [])
        return any(role.id in allowed for role in member.roles)

    async def _log_review(self, guild: discord.Guild, item: dict[str, Any], settings: dict[str, Any]) -> None:
        channel = guild.get_channel(settings.get("log_channel_id")) if settings.get("log_channel_id") else None
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            await channel.send(
                f"提案 #{item['id']} を {STATUS_LABELS.get(item['status'], item['status'])} に変更しました。担当: <@{item['reviewer_id']}>",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            LOGGER.warning("Suggestion review log failed guild=%s suggestion=%s", guild.id, item["id"])

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
                item = self.service.review(interaction.guild.id, suggestion_id, interaction.user.id, value)
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
        if action == "review":
            await self._log_review(interaction.guild, item, settings)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SuggestionsCog(bot))
