"""Ticket resource ownership, generations and retry boundaries."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cogs.community.tickets import TicketsCog
from db_support import prepare_database
from ticketing import TicketRepository
from jobs.leases import ResourceLease


class TicketResourceReviewTests(unittest.IsolatedAsyncioTestCase):
    def closed_ticket(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        repository = TicketRepository(prepare_database(Path(temporary.name) / 'tickets.db', self.addCleanup))
        repository.save_settings(1, {'enabled': True})
        team = repository.save_team(1, {'name': 'Support', 'role_ids': [50]})
        panel = repository.save_panel(1, {'name': 'Support', 'team_id': team['id'],
            'mode': 'private_thread', 'thread_parent_channel_id': 20, 'staff_notification_channel_id': 30})
        ticket = repository.reserve_ticket(1, panel['id'], 10, 'independent-review', {})
        ticket = repository.activate_ticket(ticket['id'], 100, 20)
        repository.begin_close(ticket['id'], 2, 'closed')
        return repository, repository.close_ticket(ticket['id'], 2, 'closed')

    async def test_parallel_consumers_cannot_archive_after_successful_reopen(self):
        repository, ticket = self.closed_ticket()
        entered, release = asyncio.Event(), asyncio.Event()
        external = {'archived': True}

        async def set_closed(ticket, *, closed):
            if closed:
                entered.set()
                await release.wait()
            external['archived'] = closed

        cog = SimpleNamespace(repository=repository,
            bot=SimpleNamespace(get_guild=lambda _: SimpleNamespace(get_channel_or_thread=lambda _: None)),
            discord=SimpleNamespace(set_closed=set_closed),
            service=SimpleNamespace(schedule_ticket=lambda _: None))
        item = {'ticket_id': ticket['id'], 'actor_id': 2, 'action': 'reopen', 'payload': {}}
        with patch.object(repository, 'transcript_for_ticket', return_value={'id': 1}):
            closing = asyncio.create_task(TicketsCog._deliver_outbox_item(cog,
                {'ticket_id': ticket['id'], 'actor_id': 2, 'action': 'close_resource', 'payload': {'revision': ticket['revision']}}))
            try:
                await asyncio.wait_for(entered.wait(), timeout=5)
                blocked = await TicketsCog._deliver_outbox_item(cog, item)
                self.assertTrue(blocked.retry)
                self.assertIsNotNone(blocked.error)
                self.assertEqual('closed', repository.ticket(ticket['id'])['status'])
                release.set()
                self.assertIsNone((await asyncio.wait_for(closing, timeout=5)).error)
                self.assertIsNone((await TicketsCog._deliver_outbox_item(cog, item)).error)
                # A delayed close from the previous generation must not touch Discord.
                external['archived'] = False
                stale = await TicketsCog._deliver_outbox_item(cog,
                    {'ticket_id': ticket['id'], 'actor_id': 2, 'action': 'close_resource', 'payload': {'revision': ticket['revision']}})
                self.assertEqual('revision_conflict', stale.error)
            finally:
                release.set()
                if not closing.done():
                    closing.cancel()
        self.assertEqual('open', repository.ticket(ticket['id'])['status'])
        self.assertFalse(external['archived'], 'The latest reopen must match Discord resource state')

    async def test_reopen_database_failure_retries_external_success(self):
        repository, ticket = self.closed_ticket()
        port = SimpleNamespace(set_closed=AsyncMock())
        cog = SimpleNamespace(repository=repository,
            bot=SimpleNamespace(get_guild=lambda _: None), discord=port,
            service=SimpleNamespace(schedule_ticket=lambda _: None))
        item = {'ticket_id': ticket['id'], 'actor_id': 2, 'action': 'reopen', 'payload': {}}
        with patch.object(repository, 'reopen_ticket', side_effect=RuntimeError('database unavailable')):
            failed = await TicketsCog._deliver_outbox_item(cog, item)
        self.assertTrue(failed.retry)
        self.assertEqual('closed', repository.ticket(ticket['id'])['status'])
        self.assertIsNone((await TicketsCog._deliver_outbox_item(cog, item)).error)
        self.assertEqual('open', repository.ticket(ticket['id'])['status'])
        self.assertEqual(2, port.set_closed.await_count)

    async def test_expired_reopen_owner_cannot_commit_after_discord_success(self):
        repository, ticket = self.closed_ticket()
        now = [1]
        lease = ResourceLease(repository.database_url, 'ticket_close', ticket['id'], clock=lambda: now[0])
        async def external_success_then_expire(*args, **kwargs):
            now[0] = 1000
        port = SimpleNamespace(set_closed=AsyncMock(side_effect=external_success_then_expire))
        cog = SimpleNamespace(repository=repository,
            bot=SimpleNamespace(get_guild=lambda _: None), discord=port,
            service=SimpleNamespace(schedule_ticket=lambda _: None))
        item = {'ticket_id': ticket['id'], 'actor_id': 2, 'action': 'reopen', 'payload': {}}
        # Other registry tests reload Cog modules; patch this imported callback's
        # globals so the injected clock belongs to the handler actually invoked.
        with patch.dict(TicketsCog._deliver_outbox_item.__globals__, {'ResourceLease': lambda *args, **kwargs: lease}):
            outcome = await TicketsCog._deliver_outbox_item(cog, item)
        self.assertTrue(outcome.retry)
        self.assertIsNotNone(outcome.error)
        port.set_closed.assert_awaited_once()
        self.assertEqual('closed', repository.ticket(ticket['id'])['status'])
        port.set_closed.side_effect = None
        self.assertIsNone((await TicketsCog._deliver_outbox_item(cog, item)).error)
        self.assertEqual('open', repository.ticket(ticket['id'])['status'])

