"""Suggestion message I/O and bounded receipt reconciliation."""
import discord

from discord_io import DiscordFailure
from .presentation import STATUS_LABELS, suggestion_embed, suggestion_view


class DiscordSuggestionAdapter:
    def __init__(self, bot):
        self.bot = bot

    def channel(self, guild_id, channel_id):
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise DiscordFailure('Suggestion guild unavailable', retry=True)
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            raise DiscordFailure('Suggestion channel unavailable')
        return channel

    async def publish(self, item, settings, *, recover):
        channel = self.channel(item['guild_id'], item['channel_id'])
        marker = f"Tueka suggestion:{item['id']}:{item['created_at']}"
        try:
            if recover:
                async for message in channel.history(limit=200):
                    if message.author.id == self.bot.user.id and any((embed.footer.text or '').endswith(marker) for embed in message.embeds):
                        return message.id
                raise DiscordFailure('Suggestion receipt needs reconciliation', partial=True)
            message = await channel.send(embed=suggestion_embed(item, settings), view=suggestion_view(item, settings),
                                         allowed_mentions=discord.AllowedMentions.none())
            return message.id
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500,
                                 partial=recover or exc.status >= 500) from exc

    async def sync(self, item, settings):
        try:
            message = await self.channel(item['guild_id'], item['channel_id']).fetch_message(item['message_id'])
            await message.edit(embed=suggestion_embed(item, settings), view=suggestion_view(item, settings))
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500) from exc

    async def discussion(self, item, *, recover):
        channel = self.channel(item['guild_id'], item['channel_id'])
        try:
            message = await channel.fetch_message(item['message_id'])
            thread = message.thread or channel.guild.get_thread(message.id)
            if thread is None:
                try:
                    thread = await channel.guild.fetch_channel(message.id)
                except discord.NotFound:
                    if recover:
                        raise DiscordFailure('Suggestion discussion needs reconciliation', partial=True)
                    thread = await message.create_thread(name=f"提案 #{item['id']}", auto_archive_duration=1440)
            if not isinstance(thread, discord.Thread) or thread.parent_id != channel.id or thread.id != message.id:
                raise DiscordFailure('Suggestion discussion reference invalid', partial=True)
            return thread.id
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500,
                                 partial=recover or exc.status >= 500) from exc

    async def review_log(self, item, settings, key, *, recover):
        channel = self.channel(item['guild_id'], settings['log_channel_id'])
        marker = f'Tueka suggestion log:{key}'
        try:
            if recover:
                async for message in channel.history(limit=200):
                    if message.author.id == self.bot.user.id and any(embed.footer.text == marker for embed in message.embeds):
                        return
                raise DiscordFailure('Suggestion log receipt needs reconciliation', partial=True)
            embed = discord.Embed()
            if item.get('review_reason'):
                embed.description = item['review_reason'][:1000]
            embed.set_footer(text=marker)
            await channel.send(f"提案 #{item['id']} を {STATUS_LABELS.get(item['status'], item['status'])} に変更しました。担当: <@{item['reviewer_id']}>",
                               embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500,
                                 partial=recover or exc.status >= 500) from exc
