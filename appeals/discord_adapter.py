"""Direct messages only; bounded history reconciliation never resends blindly."""
import time
import discord
from discord_io import DiscordFailure
from .delivery import DeliveryPaused


class DiscordAppealAdapter:
    def __init__(self, bot, *, send_allowed=None):
        self.bot=bot
        self.send_allowed=send_allowed

    async def notify(self, item, key, *, recover):
        if int(time.time()) >= item['expires_at']:
            raise DeliveryPaused('thread_expired')
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
            # No database lock spans transport preparation. Recheck after its
            # awaits; recovery above only reads receipts and must still proceed.
            if int(time.time()) >= item['expires_at'] or (self.send_allowed is not None and not self.send_allowed(item)):
                raise DeliveryPaused('thread_expired_or_disabled')
            message=await channel.send(embed=embed,allowed_mentions=discord.AllowedMentions.none())
            return message.id
        except discord.HTTPException as exc:
            raise DiscordFailure('dm_transport_error',retry=exc.status==429 or exc.status>=500,partial=recover or exc.status>=500) from exc
