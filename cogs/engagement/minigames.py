"""Guild-scoped minigames."""
import random
import discord
from discord import app_commands
from discord.ext import commands
from guild_settings import GuildSettingsRepository

class MinigamesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.guild_settings = GuildSettingsRepository(bot.settings.database_url)

    async def _enabled(self, interaction: discord.Interaction, module: str) -> bool:
        if interaction.guild is None or not self.guild_settings.module_enabled(interaction.guild.id, module):
            await interaction.response.send_message("この機能は管理者により無効です。", ephemeral=True)
            return False
        return True

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
    await bot.add_cog(MinigamesCog(bot))
