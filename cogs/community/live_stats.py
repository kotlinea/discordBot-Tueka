"""Update registered statistics voice channels."""
import asyncio
import logging

import discord
from discord.ext import commands, tasks

from guild_settings import GuildSettingsRepository
from template_defaults import STATS_TEMPLATE_DEFAULT


LOGGER = logging.getLogger(__name__)


class LiveStatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.guild_settings = GuildSettingsRepository(bot.settings.database_url)
        self._pending: set[int] = set()
        self._locks: dict[int, asyncio.Lock] = {}
        self.refresh_live_stats.start()
        self.flush_live_stats.start()

    def cog_unload(self) -> None:
        self.refresh_live_stats.cancel()
        self.flush_live_stats.cancel()
        self._pending.clear()
        self._locks.clear()


    async def update_stats(self, guild: discord.Guild) -> None:
        async with self._locks.setdefault(guild.id, asyncio.Lock()):
            if self.bot.get_guild(guild.id) is not guild:
                return
            try:
                await self._update_stats(guild)
            except Exception:
                LOGGER.warning("Failed to update live statistics in guild %s", guild.id, exc_info=True)
                if self.bot.get_guild(guild.id) is guild:
                    self._pending.add(guild.id)

    async def _update_stats(self, guild: discord.Guild) -> None:
        module = self.guild_settings.get_module(guild.id, "live_stats")
        if not module["enabled"]:
            return
        settings = module["settings"]
        channel_id = settings.get("stats_channel_id")
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, discord.VoiceChannel):
            return
        members = guild.member_count or len(guild.members)
        bots = sum(member.bot for member in guild.members)
        template = str(settings.get("stats_template") or STATS_TEMPLATE_DEFAULT)[:90]
        try:
            name = template.format(members=members, bots=bots, humans=members - bots, roles=len(guild.roles))
        except (KeyError, ValueError):
            name = STATS_TEMPLATE_DEFAULT.format(members=members, bots=bots, humans=members - bots, roles=len(guild.roles))
        if channel.name != name:
            await channel.edit(name=name[:100], reason="Live statistics update")

    @tasks.loop(minutes=5)
    async def refresh_live_stats(self) -> None:
        try:
            guild_ids = self.guild_settings.enabled_module_guild_ids("live_stats")
        except Exception:
            LOGGER.warning("Failed to load live statistics settings", exc_info=True)
            return
        for guild_id in guild_ids:
            guild = self.bot.get_guild(guild_id)
            if guild:
                await self.update_stats(guild)

    @tasks.loop(seconds=5)
    async def flush_live_stats(self) -> None:
        pending, self._pending = self._pending, set()
        guilds = [guild for guild_id in pending if (guild := self.bot.get_guild(guild_id)) is not None]
        await asyncio.gather(*(self.update_stats(guild) for guild in guilds))
        self._locks = {guild_id: lock for guild_id, lock in self._locks.items()
                       if lock.locked() or self.bot.get_guild(guild_id) is not None}

    @flush_live_stats.before_loop
    async def before_flush_live_stats(self) -> None:
        await self.bot.wait_until_ready()

    @refresh_live_stats.before_loop
    async def before_refresh_live_stats(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        self._pending.add(member.guild.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        self._pending.add(member.guild.id)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        self._pending.add(role.guild.id)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        self._pending.add(role.guild.id)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        self._pending.discard(guild.id)
        lock = self._locks.get(guild.id)
        if lock is not None and not lock.locked():
            self._locks.pop(guild.id, None)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LiveStatsCog(bot))
