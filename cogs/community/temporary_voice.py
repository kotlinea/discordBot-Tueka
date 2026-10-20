"""Create and recover tracked temporary voice channels under owner leases."""
import asyncio
import logging
import time

import discord
from discord.ext import commands, tasks

from community import CommunityRepository
from guild_settings import GuildSettingsRepository
from jobs import LostLease
from jobs.leases import ResourceLease
from template_defaults import TEMP_VOICE_NAME_DEFAULT


LOGGER = logging.getLogger(__name__)


class TemporaryVoiceCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repository = CommunityRepository(bot.settings.database_url)
        self.guild_settings = GuildSettingsRepository(bot.settings.database_url)
        self.cleanup_temporary_voice_channels.start()

    def cog_unload(self) -> None:
        self.cleanup_temporary_voice_channels.cancel()

    def _owner_lease(self, guild_id: int, owner_id: int) -> ResourceLease:
        return ResourceLease(self.repository.database_url, 'temporary_voice_owner', f'{guild_id}:{owner_id}')

    async def _delete_empty(self, channel, lease) -> bool:
        if channel.members:
            return False
        lease.check()
        try:
            await channel.delete(reason='Temporary voice channel became empty')
        except discord.NotFound:
            pass
        except discord.HTTPException:
            LOGGER.warning('Could not delete temporary voice channel %s', channel.id, exc_info=True)
            return False
        self.repository.remove_temporary_voice_channel(channel.id, lease=lease)
        return True

    async def _cleanup_tracked(self, guild, record, channel=None) -> None:
        async def cleanup(lease):
            current = self.repository.temporary_voice_channel(record['channel_id'])
            if current != {'guild_id': guild.id, 'owner_id': record['owner_id']}:
                return
            if not self.guild_settings.module_enabled(guild.id, 'temporary_voice'):
                return
            target = channel or guild.get_channel(record['channel_id'])
            if target is None:
                try:
                    target = await guild.fetch_channel(record['channel_id'])
                except discord.NotFound:
                    self.repository.remove_temporary_voice_channel(record['channel_id'], lease=lease)
                    return
            if getattr(getattr(target, 'guild', None), 'id', None) != guild.id:
                return
            if not hasattr(target, 'members'):
                return
            await self._delete_empty(target, lease)
        try:
            await self._owner_lease(guild.id, record['owner_id']).run(cleanup)
        except LostLease:
            return  # Creation or another cleanup still owns this member's resources.
        except Exception:
            LOGGER.warning('Could not reconcile temporary voice channel %s', record['channel_id'], exc_info=True)

    async def _compensate(self, channel, member, lease) -> None:
        try:
            if await self._delete_empty(channel, lease):
                return
        except Exception:
            LOGGER.warning('Could not compensate temporary voice channel %s', channel.id, exc_info=True)
        try:
            # Preserve a durable retry target when deletion failed or someone joined.
            self.repository.add_temporary_voice_channel(channel.id, member.guild.id, member.id, lease=lease)
        except Exception:
            await self._recover_created(channel, member)

    async def _recover_created(self, channel, member) -> None:
        # Record only the ID returned by this creation. Never delete with the
        # expired lease or overwrite another recorded owner during recovery.
        try:
            self.repository.remember_temporary_voice_cleanup(channel.id, member.guild.id, member.id)
        except Exception:
            LOGGER.error('Temporary voice requires reconciliation guild=%s channel=%s owner=%s',
                         member.guild.id, channel.id, member.id, exc_info=True)
            return
        await self._cleanup_tracked(member.guild, {'channel_id': channel.id, 'owner_id': member.id}, channel)

    async def _create_owned(self, member, after, lease) -> None:
        guild = member.guild
        module = self.guild_settings.get_module(guild.id, 'temporary_voice')
        settings = module['settings']
        trigger_id = settings.get('temp_voice_trigger_id')
        if not module['enabled'] or not trigger_id or after.channel.id != int(trigger_id):
            return
        if getattr(getattr(member, 'voice', None), 'channel', None) != after.channel:
            return
        category_id = settings.get('temp_voice_category_id')
        category = guild.get_channel(int(category_id)) if category_id else after.channel.category
        if category is not None and not isinstance(category, discord.CategoryChannel):
            return
        name = str(settings.get('temp_voice_name') or TEMP_VOICE_NAME_DEFAULT).replace('{member}', member.display_name)[:100]
        channel = None
        try:
            lease.check()
            channel = await guild.create_voice_channel(name=name, category=category, reason='Temporary voice channel')
            self.repository.add_temporary_voice_channel(channel.id, guild.id, member.id, lease=lease)
            lease.check()
            if (not self.guild_settings.module_enabled(guild.id, 'temporary_voice')
                    or getattr(getattr(member, 'voice', None), 'channel', None) != after.channel):
                await self._compensate(channel, member, lease)
                return
            await member.move_to(channel, reason='Temporary voice channel')
        except LostLease:
            if channel is not None:
                await self._recover_created(channel, member)
            raise
        except (Exception, asyncio.CancelledError):
            if channel is not None:
                await self._compensate(channel, member, lease)
            raise

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if before.channel == after.channel:
            return
        guild = member.guild
        if not self.guild_settings.module_enabled(guild.id, 'temporary_voice'):
            return
        if before.channel:
            record = self.repository.temporary_voice_channel(before.channel.id)
            if record and record['guild_id'] == guild.id:
                await self._cleanup_tracked(guild, {'channel_id': before.channel.id, **record}, before.channel)
        if after.channel is None:
            return
        settings = self.guild_settings.get_module(guild.id, 'temporary_voice')['settings']
        trigger_id = settings.get('temp_voice_trigger_id')
        if not trigger_id or after.channel.id != int(trigger_id):
            return
        try:
            await self._owner_lease(guild.id, member.id).run(lambda lease: self._create_owned(member, after, lease))
        except LostLease:
            return
        except Exception:
            LOGGER.warning('Could not create temporary voice channel for member %s', member.id, exc_info=True)

    @tasks.loop(minutes=1)
    async def cleanup_temporary_voice_channels(self) -> None:
        try:
            guild_ids = self.guild_settings.enabled_module_guild_ids('temporary_voice')
            for guild_id in guild_ids:
                guild = self.bot.get_guild(guild_id)
                if guild is not None:
                    for record in self.repository.temporary_voice_channels(guild_id):
                        # Allow Gateway voice membership to follow a completed REST move.
                        if record['created_at'] > int(time.time()) - 60:
                            continue
                        await self._cleanup_tracked(guild, record)
        except Exception:
            LOGGER.warning('Could not load temporary voice cleanup targets', exc_info=True)

    @cleanup_temporary_voice_channels.before_loop
    async def before_cleanup_temporary_voice_channels(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TemporaryVoiceCog(bot))
