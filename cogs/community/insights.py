"""Observe selected Gateway metadata without reading or storing message bodies."""
import logging

import discord
from discord.ext import commands, tasks

from insights.repository import InsightsRepository
from insights.service import InsightsService

LOGGER = logging.getLogger(__name__)


class InsightsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.repository = InsightsRepository(bot.settings.database_url)
        self.service = InsightsService(self.repository)
        self._claimed = set()
        self._ready = False
        self._purge_cursor = 0
        self.collect.start()
        self.expire.start()

    def cog_unload(self):
        self._ready = False
        self.collect.cancel()
        self.expire.cancel()
        self._release_all()

    def _release_all(self):
        for guild in tuple(self._claimed):
            # A known observation gap invalidates local ownership even if the
            # best-effort DB release fails. Collection must claim a new boundary.
            self._claimed.discard(guild)
            try:
                self.service.release(guild)
            except Exception as error:
                LOGGER.warning('Insights release failed: %s', type(error).__name__)

    @staticmethod
    def _channel(channel):
        if channel is None:
            return None
        if isinstance(channel, discord.Thread):
            if channel.is_private() or channel.parent is None:
                return None
            channel = channel.parent
        if not isinstance(channel, (discord.TextChannel, discord.ForumChannel, discord.VoiceChannel, discord.StageChannel)):
            return None
        if channel.is_nsfw():
            return None
        if channel == channel.guild.afk_channel:
            return None
        return channel.id

    def _snapshot(self, guild):
        return {member.id: channel.id
                for channel in (*guild.voice_channels, *guild.stage_channels)
                if self._channel(channel) is not None
                for member in channel.members if not member.bot}

    @commands.Cog.listener()
    async def on_ready(self):
        self._ready = False
        self._release_all()
        self._ready = True
        await self.collect()

    @commands.Cog.listener()
    async def on_disconnect(self):
        self._ready = False
        self._release_all()

    @commands.Cog.listener()
    async def on_resumed(self):
        await self.on_ready()

    @tasks.loop(seconds=30)
    async def collect(self):
        if not self._ready or not self.bot.is_ready():
            return
        try:
            enabled = set(self.repository.settings.enabled_module_guild_ids('insights'))
            available = {g.id: g for g in self.bot.guilds if not g.unavailable}
            for guild in tuple(self._claimed - (enabled & available.keys())):
                self._claimed.discard(guild)
                self.service.release(guild)
            for guild_id in sorted(enabled & available.keys()):
                try:
                    if guild_id not in self._claimed:
                        if not self.service.claim(guild_id):
                            continue
                        self._claimed.add(guild_id)
                    if not self.service.heartbeat(guild_id, self._snapshot(available[guild_id])):
                        self._claimed.discard(guild_id)
                except Exception as error:
                    LOGGER.warning('Insights collection failed: %s', type(error).__name__)
        except Exception as error:
            LOGGER.warning('Insights collection registry failed: %s', type(error).__name__)

    @collect.before_loop
    async def before_collect(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=5)
    async def expire(self):
        try:
            self._purge_cursor = self.repository.purge(after=self._purge_cursor)['cursor']
        except Exception as error:
            LOGGER.warning('Insights expiry failed: %s', type(error).__name__)

    def _can_observe(self, guild):
        return bool(self._ready and self.bot.is_ready() and guild and not guild.unavailable and guild.id in self._claimed)

    @commands.Cog.listener()
    async def on_message(self, message):
        if not self._can_observe(message.guild) or message.author.bot or message.webhook_id is not None:
            return
        channel = self._channel(message.channel)
        if channel is None:
            return
        try:
            self.service.message(message.guild.id, message.id, channel, int(message.created_at.timestamp()), bot=message.author.bot)
        except Exception as error:
            LOGGER.warning('Insights message observation failed: %s', type(error).__name__)

    def _membership(self, member, joining):
        if not self._can_observe(member.guild) or member.bot:
            return
        joined = None if member.joined_at is None else int(member.joined_at.timestamp() * 1000000)
        try:
            self.service.membership(member.guild.id, member.id, joined, joining=joining, bot=member.bot)
        except Exception as error:
            LOGGER.warning('Insights membership observation failed: %s', type(error).__name__)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        self._membership(member, True)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        self._membership(member, False)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not self._can_observe(member.guild) or member.bot:
            return
        try:
            self.service.voice(member.guild.id, member.id, self._channel(before.channel), self._channel(after.channel), bot=member.bot)
        except Exception as error:
            LOGGER.warning('Insights voice observation failed: %s', type(error).__name__)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        if guild.id in self._claimed:
            self._claimed.discard(guild.id)
            try:
                self.service.release(guild.id)
            except Exception as error:
                LOGGER.warning('Insights guild release failed: %s', type(error).__name__)


async def setup(bot):
    await bot.add_cog(InsightsCog(bot))
