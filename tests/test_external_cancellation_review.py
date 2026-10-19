"""Accepted external effects must settle before cancellation repair can run."""
import asyncio
import unittest

from giveaways.service import GiveawayService
from starboard.delivery import HighlightDelivery
from suggestions.delivery import SuggestionDeliveryService
from discord_io import settle_external


class ExternalCancellationReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_result_and_child_failure_propagate(self):
        async def operation(fail):
            if fail:
                raise RuntimeError('Generated external failure')
            return 900

        self.assertEqual(await settle_external(operation(False)), 900)
        with self.assertRaisesRegex(RuntimeError, 'Generated external failure'):
            await settle_external(operation(True))

    async def test_child_cancellation_terminates_without_parent_cancellation(self):
        async def operation():
            raise asyncio.CancelledError('Generated child cancellation')

        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(settle_external(operation()), 5)

    async def test_single_parent_cancel_waits_for_each_child_settlement(self):
        for outcome in ('result', 'error', 'cancel'):
            with self.subTest(outcome=outcome):
                await self._single_cancel_then_settle(outcome)

    async def _single_cancel_then_settle(self, outcome):
        entered, release, settled = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def operation():
            entered.set()
            try:
                await release.wait()
                if outcome == 'error':
                    raise RuntimeError('Generated failure after parent cancellation')
                if outcome == 'cancel':
                    raise asyncio.CancelledError('Generated child cancellation')
                return 900
            finally:
                settled.set()

        task = asyncio.create_task(settle_external(operation()))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            task.cancel('Generated parent cancellation')
            barrier = asyncio.get_running_loop().create_future()
            asyncio.get_running_loop().call_soon(barrier.set_result, None)
            await barrier
            self.assertFalse(task.done())
            self.assertFalse(settled.is_set())
            release.set()
            with self.assertRaisesRegex(asyncio.CancelledError, 'Generated parent cancellation'):
                await asyncio.wait_for(task, 5)
            self.assertTrue(settled.is_set())
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)

    async def test_repeated_cancellation_cannot_run_repair_before_remote_effect(self):
        for name, external in (
            ('suggestions', SuggestionDeliveryService._external),
            ('starboard', HighlightDelivery._external),
            ('giveaways', GiveawayService._external),
        ):
            with self.subTest(domain=name):
                await self._accepted_edit_then_double_cancel(external)

    async def _accepted_edit_then_double_cancel(self, external):
        accepted = asyncio.Event()
        release_remote = asyncio.Event()
        repair_started = asyncio.Event()
        rendered = {'status': 'approved'}
        order = []

        async def remote_edit():
            # Discord owns an accepted request independently of its HTTP waiter.
            accepted.set()
            await release_remote.wait()
            rendered['status'] = 'pending'
            order.append('remote_effect')

        remote = asyncio.create_task(remote_edit())

        async def request():
            # Cancelling the local request cannot retract remote acceptance.
            await asyncio.shield(remote)

        async def handler():
            try:
                await external(request())
            finally:
                # Model a repair worker draining the reservation immediately.
                repair_started.set()
                rendered['status'] = 'approved'
                order.append('repair')

        task = asyncio.create_task(handler())

        async def loop_barrier():
            # Queued task wakeups precede this callback; no timing sleeps.
            barrier = asyncio.get_running_loop().create_future()
            asyncio.get_running_loop().call_soon(barrier.set_result, None)
            await barrier

        try:
            await asyncio.wait_for(accepted.wait(), 5)
            task.cancel()
            await loop_barrier()
            # The first cancellation has reached the helper's cleanup wait.
            self.assertFalse(task.done())
            self.assertFalse(repair_started.is_set())
            task.cancel()
            await loop_barrier()
            await loop_barrier()
            self.assertEqual(task.cancelling(), 2)
            repair_before_effect = repair_started.is_set()
            release_remote.set()
            await asyncio.wait_for(asyncio.shield(remote), 5)
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(task), 5)
            self.assertEqual(
                rendered['status'], 'approved',
                f'Accepted stale edit overwrote cancellation repair: {order}; '
                f'repair ran before remote release={repair_before_effect}',
            )
            self.assertEqual(order, ['remote_effect', 'repair'])
        finally:
            release_remote.set()
            # Always settle the remote operation before final handler cleanup.
            await asyncio.gather(remote, return_exceptions=True)
            await asyncio.gather(task, return_exceptions=True)
