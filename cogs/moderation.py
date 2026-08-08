import csv

import discord
from discord import app_commands
from discord.ext import commands

from storage import GuildStorage


class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.storage = GuildStorage(bot.settings.database_path)

    def banned_words(self) -> list[str]:
        path = self.bot.settings.banned_words_file
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as file:
            return [word.strip().lower() for row in csv.reader(file) for word in row if word.strip()]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        matches = [word for word in self.banned_words() if word in message.content.lower()]
        if not matches:
            return
        warn_count = self.storage.add_warning(message.guild.id, message.author.id)
        try:
            await message.delete()
            await message.channel.send(f"⚠️ {message.author.mention} さん、不適切な発言が検出されました。\n警告数: {warn_count}")
        except discord.Forbidden:
            pass

    @app_commands.command(description="管理ログチャネルを設定します。")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def set_management(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        assert interaction.guild is not None
        self.storage.set(interaction.guild.id, "management_channel_id", channel.id)
        await interaction.response.send_message(f"管理ログチャネルを `{channel.name}` に設定しました。", ephemeral=True)

    @app_commands.command(description="このチャネルのメッセージを削除します。")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, confirm: str | None = None) -> None:
        if confirm != "confirm" or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("確認には `/clear confirm` を使用してください。", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge()
        await interaction.followup.send(f"{len(deleted)} 件を削除しました。", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationCog(bot))
