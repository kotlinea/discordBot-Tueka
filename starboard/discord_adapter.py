"""Discord SDK I/O, bounded reaction users and marker-verified highlight writes."""
from urllib.parse import urlparse
import discord
from discord_io import DiscordFailure
from .models import emoji as normalize_emoji,voter_count


def failure(exc,*,send=False):
    if isinstance(exc,discord.HTTPException):
        return DiscordFailure(f'Discord highlight request failed (status {exc.status})',retry=exc.status==429 or exc.status>=500,partial=send and exc.status>=500,missing=exc.status==404)
    return DiscordFailure('Discord highlight transport failed',retry=True,partial=send)


def embed(source,score,emoji,marker):
    url=f"https://discord.com/channels/{source['guild_id']}/{source['channel_id']}/{source['message_id']}"
    display=f'<:reaction:{emoji.split(":",1)[1]}>' if emoji.startswith('custom:') else emoji
    result=discord.Embed(title=f'{display} {score}',description=source.get('content','')[:2000] or '—',url=url,color=0xF59E0B)
    result.set_author(name=source.get('author_name','Discord member')[:80])
    result.add_field(name='Original / 元の投稿',value=f'[Discord]({url})',inline=False)
    if source.get('image_url'):result.set_image(url=source['image_url'])
    result.set_footer(text=marker)
    return result


class DiscordHighlightAdapter:
    def __init__(self,bot):self.bot=bot

    async def channel(self,guild_id,channel_id):
        guild=self.bot.get_guild(guild_id)
        if guild is None:raise DiscordFailure('Highlight Guild unavailable',retry=True)
        try:channel=guild.get_channel_or_thread(channel_id) or await guild.fetch_channel(channel_id)
        except (discord.HTTPException,OSError,TimeoutError) as exc:raise failure(exc) from exc
        if not isinstance(channel,(discord.TextChannel,discord.Thread)) or channel.guild.id!=guild_id:
            raise DiscordFailure('Highlight channel unavailable')
        return channel

    async def source(self,guild,channel,message,emoji,allow_private=False):
        try:
            target=await self.channel(guild,channel)
            parent=target.parent if isinstance(target,discord.Thread) else None
            if isinstance(target,discord.Thread) and parent is None:parent=await target.guild.fetch_channel(target.parent_id)
            nsfw=parent.is_nsfw() if parent else target.is_nsfw()
            private=isinstance(target,discord.Thread) and target.type==discord.ChannelType.private_thread
            if nsfw or (private and not allow_private):
                return {'guild_id':guild,'channel_id':channel,'message_id':message,'parent_channel_id':parent.id if parent else None,'author_id':0,'author_bot':False,'author_name':'','content':'','nsfw':nsfw,'private_thread':private,'deleted':False,'image_url':''},0
            source=await target.fetch_message(message)
            snapshot={'guild_id':guild,'channel_id':channel,'message_id':message,'parent_channel_id':parent.id if parent else None,'author_id':source.author.id,'author_bot':source.author.bot,'author_name':source.author.display_name[:80],'content':source.content[:2000],'nsfw':nsfw,'deleted':False,'image_url':''}
            if private:snapshot['private_thread']=True
            for attachment in source.attachments:
                url=urlparse(attachment.url)
                if (attachment.content_type or '').startswith('image/') and url.scheme=='https' and url.hostname in {'cdn.discordapp.com','media.discordapp.net'}:
                    snapshot['image_url']=attachment.url;break
            voters={}
            if not source.author.bot and not nsfw:
                for reaction in source.reactions:
                    raw=f'custom:{reaction.emoji.id}' if isinstance(reaction.emoji,discord.PartialEmoji) and reaction.emoji.id else str(reaction.emoji)
                    # External reactions can use emoji outside our configuration
                    # validator. They must not prevent counting the chosen emoji.
                    try:reaction_emoji=normalize_emoji(raw)
                    except ValueError:continue
                    if reaction_emoji!=emoji:continue
                    for kind in (discord.ReactionType.normal,discord.ReactionType.burst):
                        async for user in reaction.users(limit=5001,type=kind):
                            voters[user.id]={'id':user.id,'bot':user.bot}
                            if len(voters)>5000:raise DiscordFailure('Reaction user limit exceeded; no partial count published')
            return snapshot,voter_count(list(voters.values()),source.author.id)
        except (discord.HTTPException,OSError,TimeoutError) as exc:raise failure(exc) from exc

    async def reconcile(self,guild,channel,marker):
        try:
            target=await self.channel(guild,channel)
            async for message in target.history(limit=200):
                if message.author.id==self.bot.user.id and any(e.footer.text==marker for e in message.embeds):return message.id
            return None
        except (discord.HTTPException,OSError,TimeoutError) as exc:raise failure(exc) from exc

    async def send(self,guild,channel,source,score,emoji,marker):
        # Resolve failures before send have no uncertain external effect.
        try:target=await self.channel(guild,channel)
        except (discord.HTTPException,OSError,TimeoutError) as exc:raise failure(exc) from exc
        try:
            message=await target.send(embed=embed(source,score,emoji,marker),allowed_mentions=discord.AllowedMentions.none())
            return message.id
        except (discord.HTTPException,OSError,TimeoutError) as exc:raise failure(exc,send=True) from exc

    async def _owned_message(self,guild,channel,message,marker):
        result=await (await self.channel(guild,channel)).fetch_message(message)
        if result.author.id!=self.bot.user.id or not any(e.footer.text==marker for e in result.embeds):
            raise DiscordFailure('Highlight receipt ownership mismatch')
        return result

    async def edit(self,guild,channel,message,source,score,emoji,marker):
        try:
            existing=await self._owned_message(guild,channel,message,marker)
            await existing.edit(embed=embed(source,score,emoji,marker),allowed_mentions=discord.AllowedMentions.none())
        except (discord.HTTPException,OSError,TimeoutError) as exc:raise failure(exc) from exc

    async def delete(self,guild,channel,message,marker):
        try:
            existing=await self._owned_message(guild,channel,message,marker)
            await existing.delete()
        except (discord.HTTPException,OSError,TimeoutError) as exc:raise failure(exc) from exc
