"""Social notification I/O and lookup of previously sent Discord messages."""
import hashlib
from datetime import datetime, timezone

import discord

from discord_io import DiscordFailure


class DiscordSocialAdapter:
    def __init__(self, bot):
        self.bot = bot

    def _channel(self, guild_id, channel_id):
        guild = self.bot.get_guild(guild_id)
        return guild.get_channel(channel_id) if guild else None

    def available(self, guild_id, channel_id):
        return isinstance(self._channel(guild_id, channel_id), discord.TextChannel)

    async def send(self, guild_id, channel_id, content, embed, role_id, receipt_key, *, recover, created_at):
        channel = self._channel(guild_id, channel_id)
        if not isinstance(channel, discord.TextChannel):
            raise DiscordFailure('Discord channel is unavailable')
        marker = 'Tueka delivery ' + hashlib.sha256(receipt_key.encode()).hexdigest()[:24]
        value = discord.Embed.from_dict(embed)
        footer = str(embed.get('footer', {}).get('text', ''))
        value.set_footer(text=(footer[:1950] + '\n' + marker).strip())
        try:
            if recover:
                async for message in channel.history(limit=200, after=datetime.fromtimestamp(created_at - 1, timezone.utc)):
                    if message.author.id == self.bot.user.id and any(str(e.footer.text or '').endswith(marker) for e in message.embeds):
                        return message.id
                raise DiscordFailure('Delivery receipt could not be reconciled; manual review required', partial=True)
            role = channel.guild.get_role(role_id) if role_id else None
            message = await channel.send(content=(f'{role.mention}\n{content}' if role else content) or None, embed=value,
                allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=[role] if role else False))
            return message.id
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500,
                                 partial=recover or exc.status >= 500, missing=isinstance(exc, discord.NotFound)) from exc

    async def edit(self, guild_id, channel_id, message_id, embed):
        channel = self._channel(guild_id, channel_id)
        if not isinstance(channel, discord.TextChannel):
            raise DiscordFailure('Discord channel is unavailable')
        try:
            message = await channel.fetch_message(message_id)
            value = discord.Embed.from_dict(embed)
            await message.edit(embed=value, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500,
                                 missing=isinstance(exc, discord.NotFound)) from exc
