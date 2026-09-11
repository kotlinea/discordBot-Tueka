import discord
from discord import app_commands
from discord.ext import commands

from storage import GuildStorage


class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.storage = GuildStorage(bot.settings.database_path)


    @app_commands.command(description="サーバーログチャネルを設定します。")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def set_management(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        assert interaction.guild is not None
        module = self.storage.get_module(interaction.guild.id, "audit_log")
        module["settings"]["management_channel_id"] = channel.id
        self.storage.set_module(interaction.guild.id, "audit_log", enabled=module["enabled"], settings=module["settings"])
        self.storage.set(interaction.guild.id, "management_channel_id", channel.id)
        await interaction.response.send_message(f"サーバーログチャネルを `{channel.name}` に設定しました。", ephemeral=True)

    @app_commands.command(description="このチャネルのメッセージを削除します。")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, confirm: str | None = None) -> None:
        if interaction.guild and not self.storage.module_enabled(interaction.guild.id, "moderation"):
            await interaction.response.send_message("この機能は管理者により無効です。", ephemeral=True)
            return
        if confirm != "confirm" or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("確認には `/clear confirm` を使用してください。", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge()
        await interaction.followup.send(f"{len(deleted)} 件を削除しました。", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationCog(bot))
