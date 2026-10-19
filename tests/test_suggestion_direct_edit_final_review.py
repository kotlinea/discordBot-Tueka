"""Controlled stale interaction write after newer review and queue drain.
Run inside canonical test container with tests and this directory on PYTHONPATH.
This probe uses generated DB schema and fake Discord only.
"""
import asyncio
from types import SimpleNamespace
import unittest
import discord
import test_suggestions_cog

class DirectEditFailureProbe(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = test_suggestions_cog.SuggestionsCogTests.asyncSetUp
    interaction = test_suggestions_cog.SuggestionsCogTests.interaction

    async def test_partial_direct_edit_must_leave_repair_reservation(self):
        await self._direct_edit_failure(cancel=False)

    async def test_cancelled_direct_edit_finishes_before_repair(self):
        await self._direct_edit_failure(cancel=True)

    async def _direct_edit_failure(self, *, cancel):
        repo = self.cog.repository
        item = repo.create(1, 10, 20, {'idea': 'Generated proposal'})
        item = repo.attach_message(1, item['id'], 100)
        interaction = self.interaction(f"tueka-suggestion:vote:{item['id']}:up")
        entered, release = asyncio.Event(), asyncio.Event()
        rendered = {'status': None}
        async def delayed_partial_edit(**payload):
            entered.set()
            await release.wait()
            rendered['status'] = 'pending'
            if not cancel:
                raise discord.HTTPException(SimpleNamespace(status=500, reason='generated partial failure'), 'Generated response lost after remote edit')
        class Port:
            async def sync(self, snapshot, settings):
                rendered['status'] = snapshot['status']
        self.cog.delivery.port = Port()
        interaction.response.edit_message.side_effect = delayed_partial_edit
        async def drain():
            for _ in range(20):
                claim = repo.outbox_jobs.claim('probe-worker')
                if claim is None:
                    return
                result = await self.cog.delivery.deliver(claim.payload)
                self.assertIsNone(result.error)
                self.assertTrue(repo.outbox_jobs.finish(claim, result))
            self.fail('Generated probe did not drain bounded queue')
        task = asyncio.create_task(self.cog.on_interaction(interaction))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            current = repo.get(1, item['id'])
            repo.review(1, item['id'], 30, 'approved', 'Generated approval', expected_revision=current['revision'])
            await drain()
            self.assertEqual(rendered['status'], 'approved')
            if cancel:
                task.cancel()
            release.set()
            with self.assertRaises(asyncio.CancelledError if cancel else discord.HTTPException):
                await task
            await drain()
            self.assertEqual(repo.get(1, item['id'])['status'], 'approved')
            # Expected convergence. Current code leaves pending with no repair job.
            self.assertEqual(rendered['status'], 'approved', 'Stale direct edit survived after all durable jobs completed')
        finally:
            release.set()
            if not task.done():
                try:
                    await task
                except (discord.HTTPException, asyncio.CancelledError):
                    pass
