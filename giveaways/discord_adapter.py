"""Fresh Discord membership, marker-verified campaign posts and safe mentions."""
import json
import time
import discord
from discord_io import DiscordFailure


def failure(exc, *, send=False):
    if isinstance(exc, discord.HTTPException):
        return DiscordFailure(f'Discord campaign request failed (status {exc.status})', retry=exc.status == 429 or exc.status >= 500,
                              partial=send and exc.status >= 500, missing=exc.status == 404)
    return DiscordFailure('Discord campaign transport failed', retry=True, partial=send)


def presentation(plan, marker, now):
    row = plan['campaign']
    config = row['config']
    embed = discord.Embed(title=config['title'], description=config['description'] or '—', color=0x7C3AED)
    embed.add_field(name='Status / 状態', value=row['status'])
    embed.add_field(name='Entries / 参加', value=f'{plan["entrants"]} / {config["capacity"]}')
    embed.add_field(name='Deadline / 締切', value=f'<t:{row["ends_at"]}:F>')
    if plan['draw']:
        winners = json.loads(plan['draw']['winners_json'])
        embed.add_field(name=f'Result / 結果 · #{plan["draw"]["round_number"]}',
                        value=' '.join(f'<@{user}>' for user in winners) if winners else 'No winners / 当選者なし' if config['kind'] == 'giveaway' else 'Registration closed / 受付終了', inline=False)
    embed.set_footer(text=marker)
    enabled = row['status'] == 'open' and row['ends_at'] > now
    view = discord.ui.View(timeout=None)
    for action, label in (('join', 'Join / 参加'), ('leave', 'Leave / 参加を取り消す')):
        view.add_item(discord.ui.Button(label=label, custom_id=f'tueka-campaign:{row["id"]}:{action}', disabled=not enabled))
    return embed, view


class DiscordGiveawayAdapter:
    def __init__(self, bot, *, clock=time.time):
        self.bot, self.clock = bot, clock

    def guild(self, guild_id):
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise DiscordFailure('Campaign Guild unavailable', retry=True)
        return guild

    async def member(self, guild_id, user):
        try:
            member = await self.guild(guild_id).fetch_member(user)
            if member.id != user or member.guild.id != guild_id:
                raise DiscordFailure('Campaign membership scope mismatch')
            return {'id': member.id, 'guild_id': guild_id, 'bot': member.bot, 'role_ids': [role.id for role in member.roles],
                    'created_at': int(member.created_at.timestamp()), 'joined_at': int(member.joined_at.timestamp()) if member.joined_at else None}
        except discord.NotFound:
            return None
        except (discord.HTTPException, OSError, TimeoutError) as exc:
            raise failure(exc) from exc

    async def channel(self, guild_id, channel_id):
        guild = self.guild(guild_id)
        channel = guild.get_channel(channel_id) or await guild.fetch_channel(channel_id)
        if not isinstance(channel, discord.TextChannel) or channel.guild.id != guild_id:
            raise DiscordFailure('Campaign channel scope mismatch')
        return channel

    async def reconcile(self, guild_id, channel_id, marker):
        try:
            channel = await self.channel(guild_id, channel_id)
            async for message in channel.history(limit=200):
                if message.author.id == self.bot.user.id and any(embed.footer.text == marker for embed in message.embeds):
                    return message.id
            return None
        except (discord.HTTPException, OSError, TimeoutError) as exc:
            raise failure(exc) from exc

    async def send(self, plan, marker):
        row = plan['campaign']
        try:
            channel = await self.channel(row['guild_id'], row['config']['channel_id'])
        except (discord.HTTPException, OSError, TimeoutError) as exc:
            raise failure(exc) from exc
        embed, view = presentation(plan, marker, int(self.clock()))
        try:
            message = await channel.send(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
            return message.id
        except (discord.HTTPException, OSError, TimeoutError) as exc:
            raise failure(exc, send=True) from exc

    async def edit(self, plan, message, marker):
        row = plan['campaign']
        try:
            channel = await self.channel(row['guild_id'], row['config']['channel_id'])
            existing = await channel.fetch_message(message)
            if existing.author.id != self.bot.user.id or not any(embed.footer.text == marker for embed in existing.embeds):
                raise DiscordFailure('Campaign receipt ownership mismatch')
            embed, view = presentation(plan, marker, int(self.clock()))
            await existing.edit(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
        except (discord.HTTPException, OSError, TimeoutError) as exc:
            raise failure(exc) from exc
