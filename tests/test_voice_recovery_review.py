"""Transient reconciliation failures and fenced temporary-voice recovery."""
import asyncio
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock

import psycopg

from cogs.engagement.advanced_polls import AdvancedPollsCog
from cogs.community.temporary_voice import TemporaryVoiceCog
from community import CommunityRepository
from database.testing import temporary_database
from jobs import LostLease


class TemporaryVoiceRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setup_creation(self):
        cog = object.__new__(TemporaryVoiceCog)
        trigger = NS(id=10, category=None)
        guild = NS(id=1, get_channel=Mock())
        channel = NS(id=20, guild=guild, members=[], delete=AsyncMock())
        guild.create_voice_channel = AsyncMock(return_value=channel)
        member = NS(id=2, guild=guild, display_name='member', voice=NS(channel=trigger), move_to=AsyncMock())
        cog.guild_settings = NS(get_module=Mock(return_value={'enabled': True, 'settings': {'temp_voice_trigger_id': 10}}), module_enabled=Mock(return_value=True))
        tracked = {}
        def remember(channel_id, guild_id, owner_id):
            tracked.setdefault(channel_id, {'guild_id': guild_id, 'owner_id': owner_id})
        cog.repository = NS(add_temporary_voice_channel=Mock(side_effect=LostLease('expired during REST')),
            remember_temporary_voice_cleanup=Mock(side_effect=remember),
            temporary_voice_channel=lambda channel_id: tracked.get(channel_id),
            remove_temporary_voice_channel=Mock(side_effect=lambda channel_id, **kwargs: tracked.pop(channel_id, None)))
        old = NS(check=Mock())
        fresh = NS(check=Mock())
        async def run(operation):
            return await operation(fresh)
        cog._owner_lease = Mock(return_value=NS(run=run))
        return cog, member, trigger, channel, old, fresh, tracked

    async def test_lost_lease_uses_fresh_owner_before_deletion(self):
        cog, member, trigger, channel, old, fresh, tracked = self.setup_creation()
        with self.assertRaises(LostLease):
            await cog._create_owned(member, NS(channel=trigger), old)
        cog.repository.remember_temporary_voice_cleanup.assert_called_once_with(20, 1, 2)
        old.check.assert_called_once()
        fresh.check.assert_called_once()
        channel.delete.assert_awaited_once()
        cog.repository.remove_temporary_voice_channel.assert_called_once_with(20, lease=fresh)
        self.assertEqual(tracked, {})
        member.move_to.assert_not_awaited()

    async def test_competing_owner_preserves_durable_target_for_later_cleanup(self):
        cog, member, trigger, channel, old, fresh, tracked = self.setup_creation()
        available = asyncio.Event()
        async def run(operation):
            if not available.is_set():
                raise LostLease('another creator owns member')
            return await operation(fresh)
        cog._owner_lease.return_value = NS(run=run)
        with self.assertRaises(LostLease):
            await cog._create_owned(member, NS(channel=trigger), old)
        channel.delete.assert_not_awaited()
        self.assertEqual(tracked[20], {'guild_id': 1, 'owner_id': 2})
        available.set()
        await cog._cleanup_tracked(member.guild, {'channel_id': 20, 'owner_id': 2}, channel)
        channel.delete.assert_awaited_once()
        self.assertEqual(tracked, {})

    async def test_member_present_defers_cleanup(self):
        cog, member, trigger, channel, old, fresh, tracked = self.setup_creation()
        channel.members.append(member)
        with self.assertRaises(LostLease):
            await cog._create_owned(member, NS(channel=trigger), old)
        channel.delete.assert_not_awaited()
        self.assertIn(20, tracked)

    async def test_database_unavailable_logs_without_using_stale_lease(self):
        cog, member, trigger, channel, old, fresh, tracked = self.setup_creation()
        cog.repository.remember_temporary_voice_cleanup.side_effect = psycopg.OperationalError('DB offline')
        with self.assertLogs('cogs.community.temporary_voice', level='ERROR'):
            with self.assertRaises(LostLease):
                await cog._create_owned(member, NS(channel=trigger), old)
        channel.delete.assert_not_awaited()
        self.assertEqual(tracked, {})


class CleanupRegistrationTests(unittest.TestCase):
    def test_recovery_registration_does_not_replace_existing_owner(self):
        with temporary_database() as url:
            repo = CommunityRepository(url)
            repo.remember_temporary_voice_cleanup(20, 1, 2)
            repo.remember_temporary_voice_cleanup(20, 9, 99)
            self.assertEqual(repo.temporary_voice_channel(20), {'guild_id': 1, 'owner_id': 2})
