import discord
from discord.ext import commands

from storage import GuildStorage


class AuditLogCog(commands.Cog):
    """Send configured management-channel audit events."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.storage = GuildStorage(bot.settings.database_path)

    async def _channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        channel_id = self.storage.get(guild.id, "management_channel_id")
        channel = guild.get_channel(channel_id) if channel_id else None
        return channel if isinstance(channel, discord.TextChannel) else None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        channel = await self._channel(message.guild)
        if channel:
            embed = discord.Embed(color=discord.Color.green(), timestamp=message.created_at)
            embed.add_field(name=f"📨 {message.author} が #{message.channel} でメッセージ送信", value=message.content or "(本文なし)", inline=False)
            embed.set_footer(text=f"メッセージID: {message.id}")
            await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.author.bot or after.guild is None or before.content == after.content:
            return
        channel = await self._channel(after.guild)
        if channel:
            embed = discord.Embed(title="📝 メッセージ編集", color=discord.Color.orange())
            embed.add_field(name="Before", value=before.content or "(本文なし)", inline=False)
            embed.add_field(name="After", value=after.content or "(本文なし)", inline=False)
            await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        channel = await self._channel(message.guild)
        if channel:
            await channel.send(embed=discord.Embed(title="🗑️ メッセージ削除", description=message.content or "(本文なし)", color=discord.Color.red()))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AuditLogCog(bot))
