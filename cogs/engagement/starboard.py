"""Raw message/reaction normalization and bounded durable highlight maintenance."""
import logging
import os
import socket
import discord
from discord.ext import commands,tasks
from discord_io import DiscordFailure
from jobs import run_batch,Outcome
from starboard.repository import StarboardRepository
from starboard.delivery import HighlightDelivery
from starboard.discord_adapter import DiscordHighlightAdapter
from starboard.models import emoji as normalize_emoji

LOGGER=logging.getLogger('tueka.starboard')


class StarboardCog(commands.Cog):
    def __init__(self,bot):
        self.bot=bot;self.repository=StarboardRepository(bot.settings.database_url)
        self.adapter=DiscordHighlightAdapter(bot)
        self.delivery=HighlightDelivery(self.repository,self.adapter)
        self.owner=f'starboard:{socket.gethostname()}:{os.getpid()}'

    async def cog_load(self):self.maintenance.start()
    def cog_unload(self):self.maintenance.cancel()

    @tasks.loop(seconds=5)
    async def maintenance(self):
        try:
            self.repository.purge_expired()
            await run_batch(self.repository.refresh_jobs,self.owner+':source',self.refresh_job,limit=10)
            await run_batch(self.repository.jobs,self.owner,self.delivery.handle,limit=10)
        except Exception as exc:LOGGER.error('Highlight maintenance failed type=%s',type(exc).__name__)

    @maintenance.before_loop
    async def ready(self):await self.bot.wait_until_ready()

    async def refresh(self,guild,channel,message,reaction=None):
        if not guild or not self.repository.settings.get_module(guild,'starboard')['enabled']:return
        try:
            target=self.bot.get_guild(guild)
            cached=target.get_channel_or_thread(channel) if target else None
            parent=cached.parent_id if isinstance(cached,discord.Thread) else None
            self.repository.enqueue_refresh(guild,channel,message,known_channel=cached is not None,parent=parent,reaction=normalize_emoji(reaction) if reaction is not None else None)
        except Exception as exc:LOGGER.warning('Highlight observation enqueue failed type=%s',type(exc).__name__)

    async def refresh_job(self,job):
        guild,channel,message=job['guild_id'],job['channel_id'],job['message_id']
        if int(self.repository.clock())-job['created_at']>86400:return Outcome('Source observation expired')
        try:
            if not self.repository.settings.get_module(guild,'starboard')['enabled']:return Outcome('Starboard disabled',retry=True)
            async with self.delivery.source_lock:
                for board in self.repository.boards(guild):
                    config=board['config']
                    if not config['enabled']:continue
                    # A thread's parent may be the configured source. Resolve only
                    # channel metadata before deciding whether message content is in scope.
                    try:target=await self.adapter.channel(guild,channel)
                    except DiscordFailure as failure:
                        if not failure.missing:raise
                        self.repository.delete_channel(guild,channel);continue
                    parent=target.parent_id if isinstance(target,discord.Thread) else None
                    if not {channel,parent}&set(config['source_channel_ids']) or {channel,parent}&set(config['excluded_channel_ids']):continue
                    try:source,score=await self.adapter.source(guild,channel,message,config['emoji'],channel in config['source_channel_ids'])
                    except DiscordFailure as failure:
                        if failure.missing:self.repository.delete_source(guild,channel,[message])
                        else:raise
                    else:self.repository.observe(guild,board['id'],board['revision'],source,score)
            return Outcome()
        except DiscordFailure as failure:return Outcome(str(failure),retry=failure.retry)
        except Exception as exc:return Outcome(f'Highlight source processing failed ({type(exc).__name__})',retry=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self,payload):await self.refresh(payload.guild_id,payload.channel_id,payload.message_id,str(payload.emoji))
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self,payload):await self.refresh(payload.guild_id,payload.channel_id,payload.message_id,str(payload.emoji))
    @commands.Cog.listener()
    async def on_raw_reaction_clear(self,payload):await self.refresh(payload.guild_id,payload.channel_id,payload.message_id)
    @commands.Cog.listener()
    async def on_raw_reaction_clear_emoji(self,payload):await self.refresh(payload.guild_id,payload.channel_id,payload.message_id,str(payload.emoji))
    @commands.Cog.listener()
    async def on_raw_message_edit(self,payload):await self.refresh(payload.guild_id,payload.channel_id,payload.message_id)

    async def deleted(self,guild,channel,messages):
        if not guild:return
        try:
            async with self.delivery.source_lock:self.repository.delete_source(guild,channel,messages)
        except Exception as exc:LOGGER.warning('Highlight source deletion failed type=%s',type(exc).__name__)

    @commands.Cog.listener()
    async def on_raw_message_delete(self,payload):await self.deleted(payload.guild_id,payload.channel_id,[payload.message_id])
    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self,payload):await self.deleted(payload.guild_id,payload.channel_id,payload.message_ids)

    async def channel_deleted(self,guild,channel):
        try:
            async with self.delivery.source_lock:self.repository.delete_channel(guild,channel)
        except Exception as exc:LOGGER.warning('Highlight channel deletion failed type=%s',type(exc).__name__)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self,channel):await self.channel_deleted(channel.guild.id,channel.id)
    @commands.Cog.listener()
    async def on_guild_channel_update(self,before,after):
        if hasattr(after,'is_nsfw') and after.is_nsfw() and not before.is_nsfw():await self.channel_deleted(after.guild.id,after.id)
    @commands.Cog.listener()
    async def on_raw_thread_delete(self,payload):await self.channel_deleted(payload.guild_id,payload.thread_id)


async def setup(bot):await bot.add_cog(StarboardCog(bot))
