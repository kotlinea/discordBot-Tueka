"""Temporary voice external effects and recovery against dedicated UUID schemas."""
import asyncio
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import discord
from discord.ext import tasks

from cogs.community.temporary_voice import TemporaryVoiceCog
from database.testing import temporary_database
from database import transaction
from guild_settings import GuildSettingsRepository


def http_error(status):
    return discord.HTTPException(NS(status=status, reason='injected'), 'voice boundary test')


class TemporaryVoiceBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.url = self.enterContext(temporary_database())
        self.settings = GuildSettingsRepository(self.url)
        self.settings.set_module(1, 'temporary_voice', enabled=True,
            settings={'temp_voice_trigger_id': 10, 'temp_voice_category_id': None})
        self.category = MagicMock(spec=discord.CategoryChannel)
        self.category.id = 33
        self.trigger = NS(id=10, category=self.category, members=[])
        self.channels = {10: self.trigger, 33: self.category}
        self.created = []
        async def create(**kwargs):
            channel = NS(id=100 + len(self.created), guild=self.guild, members=[], delete=AsyncMock(), kwargs=kwargs)
            self.created.append(channel)
            self.channels[channel.id] = channel
            return channel
        self.guild = NS(id=1, get_channel=self.channels.get,
            create_voice_channel=AsyncMock(side_effect=create), fetch_channel=AsyncMock())
        self.bot = NS(settings=NS(database_url=self.url), guilds=[self.guild],
            get_guild=lambda key: self.guild if key == 1 else None, wait_until_ready=AsyncMock())
        # Drive loop bodies explicitly; do not run background timers in a test.
        with patch.object(tasks.Loop, 'start'):
            self.cog = TemporaryVoiceCog(self.bot)
        self.member = NS(id=20, display_name='member', guild=self.guild,
            voice=NS(channel=self.trigger), move_to=AsyncMock())
        async def move(channel, **kwargs):
            self.member.voice.channel = channel
            channel.members.append(self.member)
        self.member.move_to.side_effect = move

    async def asyncTearDown(self):
        unload = getattr(self.cog, 'cog_unload', None)
        if unload:
            unload()

    async def join(self, before=None):
        await self.cog.on_voice_state_update(self.member, NS(channel=before), NS(channel=self.trigger))

    def tracked(self, channel_id):
        return self.cog.repository.temporary_voice_channel(channel_id)

    def age_channel(self, channel_id):
        with transaction(self.url) as connection:
            connection.execute('UPDATE temporary_voice_channels SET created_at=0 WHERE channel_id=%s', (channel_id,))

    async def test_same_channel_voice_state_change_does_not_create(self):
        await self.join(self.trigger)
        self.guild.create_voice_channel.assert_not_awaited()

    async def test_parallel_join_for_same_member_creates_and_moves_once(self):
        entered, release = asyncio.Event(), asyncio.Event()
        original = self.guild.create_voice_channel.side_effect
        async def create(**kwargs):
            entered.set()
            await release.wait()
            return await original(**kwargs)
        self.guild.create_voice_channel.side_effect = create
        first = asyncio.create_task(self.join())
        await entered.wait()
        second = asyncio.create_task(self.join())
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(first, second)
        self.assertEqual(self.guild.create_voice_channel.await_count, 1)
        self.assertEqual(self.member.move_to.await_count, 1)

    async def test_failed_empty_delete_retains_tracking_until_success(self):
        channel = NS(id=200, guild=self.guild, members=[], delete=AsyncMock(side_effect=http_error(403)))
        self.channels[200] = channel
        self.cog.repository.add_temporary_voice_channel(200, 1, 20)
        await self.cog.on_voice_state_update(self.member, NS(channel=channel), NS(channel=None))
        self.assertIsNotNone(self.tracked(200))
        channel.delete.side_effect = None
        await self.cog.on_voice_state_update(self.member, NS(channel=channel), NS(channel=None))
        self.assertIsNone(self.tracked(200))

    async def test_already_deleted_channel_clears_tracking(self):
        channel = NS(id=200, guild=self.guild, members=[],
            delete=AsyncMock(side_effect=discord.NotFound(NS(status=404, reason='gone'), 'gone')))
        self.cog.repository.add_temporary_voice_channel(200, 1, 20)
        await self.cog.on_voice_state_update(self.member, NS(channel=channel), NS(channel=None))
        self.assertIsNone(self.tracked(200))

    async def test_db_registration_failure_compensates_created_empty_channel(self):
        with patch.object(self.cog.repository, 'add_temporary_voice_channel', side_effect=RuntimeError('injected DB failure')):
            await self.join()
        self.assertEqual(len(self.created), 1)
        self.created[0].delete.assert_awaited_once()
        self.member.move_to.assert_not_awaited()

    async def test_move_failure_compensates_created_empty_channel(self):
        self.member.move_to.side_effect = http_error(403)
        await self.join()
        self.created[0].delete.assert_awaited_once()
        self.assertIsNone(self.tracked(self.created[0].id))

    async def test_failed_compensation_preserves_tracking_for_later_retry(self):
        original = self.guild.create_voice_channel.side_effect
        async def create(**kwargs):
            channel = await original(**kwargs)
            channel.delete.side_effect = http_error(403)
            return channel
        self.guild.create_voice_channel.side_effect = create
        self.member.move_to.side_effect = http_error(403)
        await self.join()
        self.created[0].delete.assert_awaited_once()
        self.assertIsNotNone(self.tracked(self.created[0].id))

    async def test_no_explicit_category_uses_trigger_category(self):
        await self.join()
        self.assertIs(self.created[0].kwargs['category'], self.category)

    async def test_move_failure_does_not_delete_channel_someone_joined(self):
        original = self.guild.create_voice_channel.side_effect
        async def create(**kwargs):
            channel = await original(**kwargs)
            channel.members.append(NS(id=99))
            return channel
        self.guild.create_voice_channel.side_effect = create
        self.member.move_to.side_effect = http_error(403)
        await self.join()
        self.created[0].delete.assert_not_awaited()
        self.assertIsNotNone(self.tracked(self.created[0].id))

    async def test_off_preserves_empty_channel_and_reenabled_cleanup_recovers(self):
        channel = NS(id=200, guild=self.guild, members=[], delete=AsyncMock())
        self.channels[200] = channel
        self.cog.repository.add_temporary_voice_channel(200, 1, 20)
        self.age_channel(200)
        self.settings.set_module(1, 'temporary_voice', enabled=False)
        await TemporaryVoiceCog.cleanup_temporary_voice_channels.coro(self.cog)
        await self.join()
        channel.delete.assert_not_awaited()
        self.guild.create_voice_channel.assert_not_awaited()
        self.assertIsNotNone(self.tracked(200))
        self.settings.set_module(1, 'temporary_voice', enabled=True)
        await TemporaryVoiceCog.cleanup_temporary_voice_channels.coro(self.cog)
        channel.delete.assert_awaited_once()
        self.assertIsNone(self.tracked(200))

    async def test_restart_cleanup_preserves_occupied_and_missing_cache_tracking(self):
        occupied = NS(id=200, guild=self.guild, members=[self.member], delete=AsyncMock())
        self.channels[200] = occupied
        self.cog.repository.add_temporary_voice_channel(200, 1, 20)
        self.cog.repository.add_temporary_voice_channel(201, 1, 20)
        self.age_channel(200)
        self.age_channel(201)
        self.guild.fetch_channel.side_effect = http_error(403)
        await TemporaryVoiceCog.cleanup_temporary_voice_channels.coro(self.cog)
        occupied.delete.assert_not_awaited()
        self.assertIsNotNone(self.tracked(200))
        self.assertIsNotNone(self.tracked(201))

    async def test_other_instance_cleanup_cannot_delete_channel_during_move(self):
        entered, release = asyncio.Event(), asyncio.Event()
        original = self.member.move_to.side_effect
        async def move(channel, **kwargs):
            entered.set()
            await release.wait()
            await original(channel, **kwargs)
        self.member.move_to.side_effect = move
        task = asyncio.create_task(self.join())
        await entered.wait()
        self.age_channel(self.created[0].id)  # Exercise Lease, independently of the grace period.
        with patch.object(tasks.Loop, 'start'):
            other = TemporaryVoiceCog(self.bot)
        try:
            await TemporaryVoiceCog.cleanup_temporary_voice_channels.coro(other)
            self.created[0].delete.assert_not_awaited()
        finally:
            release.set()
            await task
            other.cog_unload()

    async def test_cancel_during_move_compensates_only_its_created_channel(self):
        entered = asyncio.Event()
        async def move(*args, **kwargs):
            entered.set()
            await asyncio.Event().wait()
        self.member.move_to.side_effect = move
        task = asyncio.create_task(self.join())
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.created[0].delete.assert_awaited_once()
        self.assertIsNone(self.tracked(self.created[0].id))

    async def test_periodic_cleanup_waits_for_recent_channel_membership(self):
        channel = NS(id=200, guild=self.guild, members=[], delete=AsyncMock())
        self.channels[200] = channel
        self.cog.repository.add_temporary_voice_channel(200, 1, 20)
        await TemporaryVoiceCog.cleanup_temporary_voice_channels.coro(self.cog)
        channel.delete.assert_not_awaited()
