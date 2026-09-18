"""Guild-scoped polls and small community games."""
import random
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from engagement import EngagementRepository
from guild_settings import GuildSettingsRepository


class EngagementCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.engagement_repository = EngagementRepository(bot.settings.database_url)
        self.guild_settings = GuildSettingsRepository(bot.settings.database_url)
        self.close_expired_polls.start()

    def cog_unload(self) -> None:
        self.close_expired_polls.cancel()

    async def _enabled(self, interaction: discord.Interaction, module: str) -> bool:
        if interaction.guild is None or not self.guild_settings.module_enabled(interaction.guild.id, module):
            await interaction.response.send_message("この機能は管理者により無効です。", ephemeral=True)
            return False
        return True

    @staticmethod
    def _embed(question: str, options: list[str], counts: list[int] | None = None, image_url: str | None = None) -> discord.Embed:
        counts = counts or [0] * len(options)
        embed = discord.Embed(title="投票", description=question, color=discord.Color.blurple())
        embed.add_field(name="選択肢", value="\n".join(f"{index + 1}. {option} — **{counts[index]}**票" for index, option in enumerate(options)), inline=False)
        embed.set_footer(text="ボタンを押すと投票・変更できます。")
        if image_url:
            embed.set_image(url=image_url)
        return embed

    @staticmethod
    def _view(message_id: int, options: list[str], disabled: bool = False) -> discord.ui.View:
        view = discord.ui.View(timeout=None)
        for index, option in enumerate(options):
            view.add_item(discord.ui.Button(label=f"{index + 1}. {option}"[:80], style=discord.ButtonStyle.secondary, custom_id=f"tueka-poll:{message_id}:{index}", disabled=disabled))
        return view

    @app_commands.command(description="最大10択のボタン投票を作成します。選択肢は | で区切ります。")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def poll(self, interaction: discord.Interaction, question: str, options: str, duration_minutes: app_commands.Range[int, 1, 10080] | None = None, image_url: str | None = None) -> None:
        if not await self._enabled(interaction, "advanced_polls"):
            return
        choices = [choice.strip() for choice in options.split("|") if choice.strip()]
        if not 2 <= len(choices) <= 10 or any(len(choice) > 70 for choice in choices) or len(question) > 256:
            await interaction.response.send_message("質問は256文字以内、選択肢は2〜10件・各70文字以内で入力してください。", ephemeral=True)
            return
        if image_url and not image_url.startswith(("https://", "http://")):
            await interaction.response.send_message("画像URLは http:// または https:// を指定してください。", ephemeral=True)
            return
        await interaction.response.send_message(embed=self._embed(question, choices, image_url=image_url))
        message = await interaction.original_response()
        assert interaction.guild is not None and interaction.channel is not None
        closes_at = int(time.time()) + duration_minutes * 60 if duration_minutes else None
        self.engagement_repository.create_poll(message.id, interaction.guild.id, interaction.channel.id, interaction.user.id, question, choices, image_url, closes_at)
        await message.edit(view=self._view(message.id, choices))

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.type is not discord.InteractionType.component or interaction.message is None or interaction.guild is None:
            return
        custom_id = (interaction.data or {}).get("custom_id", "")
        if not isinstance(custom_id, str) or not custom_id.startswith("tueka-poll:"):
            return
        try:
            _, message_id, raw_option = custom_id.split(":")
            message_id, option = int(message_id), int(raw_option)
        except ValueError:
            return
        poll = self.engagement_repository.poll(message_id)
        if not poll or poll["guild_id"] != interaction.guild.id or not self.guild_settings.module_enabled(interaction.guild.id, "advanced_polls"):
            await interaction.response.send_message("この投票は現在利用できません。", ephemeral=True)
            return
        counts = self.engagement_repository.cast_poll_vote(message_id, interaction.user.id, option)
        if counts is None:
            await interaction.response.send_message("この投票は終了しています。", ephemeral=True)
            return
        await interaction.response.edit_message(embed=self._embed(poll["question"], poll["options"], counts, poll.get("image_url")), view=self._view(message_id, poll["options"]))

    @tasks.loop(seconds=30)
    async def close_expired_polls(self) -> None:
        for poll in self.engagement_repository.close_expired_polls():
            guild = self.bot.get_guild(poll["guild_id"])
            channel = guild.get_channel(poll["channel_id"]) if guild else None
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                message = await channel.fetch_message(poll["message_id"])
                options = __import__("json").loads(poll["options_json"])
                await message.edit(view=self._view(message.id, options, disabled=True))
            except discord.HTTPException:
                continue

    @close_expired_polls.before_loop
    async def before_close_expired_polls(self) -> None:
        await self.bot.wait_until_ready()

    @app_commands.command(description="じゃんけんでBotと対戦します。")
    @app_commands.guild_only()
    @app_commands.choices(hand=[app_commands.Choice(name="グー", value="rock"), app_commands.Choice(name="パー", value="paper"), app_commands.Choice(name="チョキ", value="scissors")])
    async def rps(self, interaction: discord.Interaction, hand: app_commands.Choice[str]) -> None:
        if not await self._enabled(interaction, "minigames"):
            return
        choices = ("rock", "paper", "scissors")
        opponent = random.choice(choices)
        player = hand.value
        result = "引き分けです。" if player == opponent else "あなたの勝ちです！" if (player, opponent) in (("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")) else "Botの勝ちです。"
        labels = {"rock": "グー", "paper": "パー", "scissors": "チョキ"}
        await interaction.response.send_message(f"あなた: {labels[player]} / Bot: {labels[opponent]} — {result}")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EngagementCog(bot))
