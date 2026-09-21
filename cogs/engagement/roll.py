import discord
from discord import app_commands
from discord.ext import commands
import math
import random
MAX_ROLL_SIDES = 1_000_000


class RollCog(commands.Cog):
    help_category = "基本"

    @app_commands.command(description="指定された乱数を振ります。", extras={'help_order': 4})
    async def roll(self, interaction: discord.Interaction, sides: float = 6.0) -> None:
        if not math.isfinite(sides) or sides <= 0 or sides > MAX_ROLL_SIDES:
            await interaction.response.send_message(f"1 から {MAX_ROLL_SIDES:,} までの有限な正の数を指定してください。", ephemeral=True)
        elif sides.is_integer():
            await interaction.response.send_message(f"({int(sides)}面)の出目: {random.randint(1, int(sides))}")
        else:
            await interaction.response.send_message(f"範囲: 0～{sides}、結果: {random.uniform(0, sides):.2f}")




async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RollCog())
