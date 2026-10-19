"""Direct messages only; bounded history reconciliation never resends blindly."""
import time
import discord
from discord_io import DiscordFailure


class DiscordAppealAdapter:
    def __init__(self, bot):
        self.bot=bot

    async def notify(self, item, key, *, recover):
        if int(time.time()) >= item['expires_at']:
            raise DiscordFailure('thread_expired')
        marker=f'Tueka private conversation:{key}'
        try:
            user=await self.bot.fetch_user(item['author_id'])
            channel=await user.create_dm()
            if recover:
                async for message in channel.history(limit=200):
                    if message.author.id == self.bot.user.id and any(e.footer.text == marker for e in message.embeds):
                        return message.id
                raise DiscordFailure('dm_receipt_requires_reconciliation',partial=True)
            embed=discord.Embed(title=f"Tueka #{item['id']} · {item['guild_id']}",description=item['body'][:2000])
            embed.set_footer(text=marker)
            message=await channel.send(embed=embed,allowed_mentions=discord.AllowedMentions.none())
            return message.id
        except discord.HTTPException as exc:
            raise DiscordFailure('dm_transport_error',retry=exc.status==429 or exc.status>=500,partial=recover or exc.status>=500) from exc
