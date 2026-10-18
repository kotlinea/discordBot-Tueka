"""Discord I/O and bounded receipt reconciliation for messages and external events."""
import time
from datetime import datetime, timezone
import discord
from discord_io import DiscordFailure


class DiscordScheduleAdapter:
    def __init__(self, bot):
        self.bot = bot

    async def deliver(self, job, *, recover):
        payload = job['payload']
        marker = f"Tueka schedule:{job['id']}"
        guild = self.bot.get_guild(job['guild_id'])
        if not guild:
            raise DiscordFailure('schedule_guild_unavailable', retry=True, partial=recover)
        try:
            if payload['kind'] == 'event':
                if recover:
                    for event in await guild.fetch_scheduled_events():
                        if event.creator_id == self.bot.user.id and (event.description or '').endswith('\n'+marker):
                            return event.id
                    raise DiscordFailure('event_receipt_requires_reconciliation', partial=True)
                if int(time.time()) > job['deadline'] or int(time.time()) >= payload['event_start']:
                    raise DiscordFailure('event_deadline_passed')
                if not guild.me.guild_permissions.manage_events:
                    raise DiscordFailure('manage_events_required')
                # Discord allows 1000 characters including the receipt suffix.
                budget = 1000 - len(marker) - 1
                body = payload['body']
                if len(body) > budget:
                    body = body[:budget - 1] + '…'
                event = await guild.create_scheduled_event(
                    name=payload['title'], description=body+'\n'+marker,
                    start_time=datetime.fromtimestamp(payload['event_start'],timezone.utc),
                    end_time=datetime.fromtimestamp(payload['event_end'],timezone.utc),
                    entity_type=discord.EntityType.external, privacy_level=discord.PrivacyLevel.guild_only,
                    location=payload['event_location'], reason='Tueka scheduled event')
                return event.id
            channel = await self.bot.fetch_channel(payload['channel_id'])
            if not isinstance(channel, discord.TextChannel) or channel.guild.id != guild.id:
                raise DiscordFailure('schedule_channel_invalid')
            permissions = channel.permissions_for(guild.me)
            if not permissions.view_channel or not permissions.read_message_history:
                raise DiscordFailure('schedule_read_permission_required', partial=recover)
            if recover:
                async for message in channel.history(limit=200):
                    if message.author.id == self.bot.user.id and any(e.footer.text == marker for e in message.embeds):
                        return message.id
                raise DiscordFailure('message_receipt_requires_reconciliation', partial=True)
            if int(time.time()) > job['deadline']:
                raise DiscordFailure('message_deadline_passed')
            if not permissions.send_messages or not permissions.embed_links:
                raise DiscordFailure('schedule_send_permission_required')
            embed = discord.Embed(title=payload['title'] or None, description=payload['body'] or None, color=payload['color'])
            embed.set_footer(text=marker)
            message = await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            return message.id
        except discord.HTTPException as exc:
            raise DiscordFailure('schedule_transport_error', retry=exc.status==429 or exc.status>=500, partial=recover or exc.status>=500) from exc
