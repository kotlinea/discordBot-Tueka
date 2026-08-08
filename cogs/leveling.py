import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from storage import GuildStorage


def calculate_level(xp: int) -> tuple[int, int]:
    level = 0
    while xp >= required_xp(level):
        xp -= required_xp(level)
        level += 1
    return level, xp


def required_xp(level: int) -> int:
    return 5 * level**2 + 50 * level + 100


class LevelingCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.storage = GuildStorage(bot.settings.database_path)
        self.last_xp_time: dict[tuple[int, int], float] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if not self.storage.module_enabled(message.guild.id, "leveling"):
            return
        key = (message.guild.id, message.author.id)
        now = time.monotonic()
        if now - self.last_xp_time.get(key, 0) < 60:
            return
        old_user = self.storage.get_user(message.guild.id, message.author.id)
        old_level, _ = calculate_level(old_user["xp"])
        user = self.storage.add_xp(message.guild.id, message.author.id, random.randint(15, 25))
        new_level, _ = calculate_level(user["xp"])
        self.last_xp_time[key] = now
        if new_level > old_level:
            channel_id = self.storage.get(message.guild.id, "management_channel_id")
            channel = message.guild.get_channel(channel_id) if channel_id else None
            if isinstance(channel, discord.abc.Messageable):
                await channel.send(f"🎉 {message.author.mention} レベルアップ！ **Lv {new_level}**")

    @app_commands.command(description="現在のレベルを確認します。")
    @app_commands.guild_only()
    async def rank(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        if not self.storage.module_enabled(interaction.guild.id, "leveling"):
            await interaction.response.send_message("この機能は管理者により無効です。", ephemeral=True)
            return
        xp = self.storage.get_user(interaction.guild.id, interaction.user.id)["xp"]
        level, progress = calculate_level(xp)
        await interaction.response.send_message(f"📊 {interaction.user.mention} のレベル: **Lv {level}**\n現在のXP: {progress} / {required_xp(level)}")

    @app_commands.command(description="トップ5のXPランキングを表示します。")
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        if not self.storage.module_enabled(interaction.guild.id, "leveling"):
            await interaction.response.send_message("この機能は管理者により無効です。", ephemeral=True)
            return
        ranked = self.storage.leaderboard(interaction.guild.id)
        if not ranked:
            await interaction.response.send_message("まだXPデータがありません。")
            return
        lines = [f"**{i}.** <@{data['user_id']}> - {data['xp']} XP (Lv.{calculate_level(data['xp'])[0]})" for i, data in enumerate(ranked, 1)]
        await interaction.response.send_message("🏆 **XPランキング** 🏆\n" + "\n".join(lines))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LevelingCog(bot))
