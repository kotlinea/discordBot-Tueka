"""Ticket rename authorization boundaries."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord

from cogs.community.tickets import TicketsCog


class TicketRenameReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_rename_rejects_nonstaff_before_bot_operation(self):
        channel = Mock(spec=discord.TextChannel)
        interaction = SimpleNamespace(channel_id=10, guild_id=1, channel=channel,
            user=Mock(spec=discord.Member), response=SimpleNamespace(send_message=AsyncMock()))
        interaction.user.id = 10
        ticket = {'id': 1, 'guild_id': 1, 'panel_id': 3, 'opener_id': 10}
        cog = SimpleNamespace(repository=SimpleNamespace(ticket_for_container=lambda _: ticket,
            panel=lambda *args: {'team_id': 2}), discord=SimpleNamespace(rename=AsyncMock()),
            _staff=AsyncMock(return_value=False))
        await TicketsCog.rename.callback(cog, interaction, 'changed-by-opener')
        cog.discord.rename.assert_not_awaited()
        interaction.response.send_message.assert_awaited_once()

