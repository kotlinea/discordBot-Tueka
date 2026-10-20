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


class PollRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def cog(self):
        cog = object.__new__(AdvancedPollsCog)
        cog.engagement_repository = NS(close_expired_polls=Mock(), pending_poll_displays=Mock(return_value=[10, 20]))
        cog._sync_poll = AsyncMock()
        return cog

    async def test_transient_database_failure_reaches_next_real_loop_tick(self):
        cog = self.cog()
        recovered = asyncio.Event()
        cog.engagement_repository.close_expired_polls.side_effect = [psycopg.OperationalError('synthetic disconnect'), None]
        cog.engagement_repository.pending_poll_displays.return_value = []
        def pending():
            recovered.set()
            return []
        cog.engagement_repository.pending_poll_displays.side_effect = pending
        cog.bot = NS(wait_until_ready=AsyncMock())
        loop = cog.close_expired_polls
        loop.change_interval(seconds=0.01)
        task = loop.start()
        try:
            await asyncio.wait_for(recovered.wait(), 2)
            self.assertFalse(loop.failed())
        finally:
            loop.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_failed_poll_does_not_block_other_poll_and_retries_next_tick(self):
        cog = self.cog()
        cog._sync_poll.side_effect = [psycopg.OperationalError('poll read'), None, None, None]
        await AdvancedPollsCog.close_expired_polls.coro(cog)
        await AdvancedPollsCog.close_expired_polls.coro(cog)
        self.assertEqual([call.args[0] for call in cog._sync_poll.await_args_list], [10, 20, 10, 20])

    async def test_enumeration_failure_is_retried(self):
        cog = self.cog()
        cog.engagement_repository.pending_poll_displays.side_effect = [psycopg.OperationalError('enumeration'), [20]]
        await AdvancedPollsCog.close_expired_polls.coro(cog)
        await AdvancedPollsCog.close_expired_polls.coro(cog)
        cog._sync_poll.assert_awaited_once_with(20)

    async def test_cancellation_propagates(self):
        cog = self.cog()
        cog._sync_poll.side_effect = asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await AdvancedPollsCog.close_expired_polls.coro(cog)
        cog._sync_poll.assert_awaited_once_with(10)


