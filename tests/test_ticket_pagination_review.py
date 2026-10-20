"""Ticket assigned-team pagination boundaries."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from dashboard.api.community.tickets import create_router
from dashboard.api.community.ticket_support.dependencies import TicketDependencies


class TicketPaginationReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_items_keeps_cursor_when_first_page_belongs_to_another_team(self):
        rows = [dict(id=i, guild_id=1, panel_id=2 if i > 1 else 1) for i in range(101, 0, -1)]
        repository = SimpleNamespace(tickets=lambda guild_id, status=None, before=None:
            [row for row in rows if before is None or row['id'] < before][:100])
        context = SimpleNamespace(dashboard_repository=None, discord=None, settings=None,
            ticket_repository=repository, ticket_transcripts=None, ticket_service=object())

        async def subject(access, request, guild_id, ticket, actor, administrator):
            if ticket['panel_id'] != 1:
                raise HTTPException(403)

        with patch.object(TicketDependencies, 'ticket_subject_access', subject):
            router = create_router(context)
            route = next(route for route in router.routes if route.path == '/guilds/{guild_id}/tickets/items')
            first = await route.endpoint(SimpleNamespace(method='GET'), 1, None, None, (20, False))
            self.assertIsNotNone(first['next'], 'An inaccessible page must not end pagination')
            second = await route.endpoint(SimpleNamespace(method='GET'), 1, None, first['next'], (20, False))
            self.assertEqual([1], [item['id'] for item in second['items']])

