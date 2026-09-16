import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord

from discord_io import DiscordFailure
from ticketing.discord_adapter import DiscordTicketAdapter


class TicketDiscordAdapterTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self, channel):
        guild = SimpleNamespace(id=1, get_channel_or_thread=lambda _: channel)
        bot = SimpleNamespace(user=SimpleNamespace(id=99), get_guild=lambda _: guild)
        return DiscordTicketAdapter(bot)

    async def test_notice_recovery_rejects_foreign_author_and_prefix_collision(self):
        marker = 'Tueka ticket notice:30:1000'
        messages = []
        for author, footer in ((100, marker), (99, marker + '1')):
            embed = discord.Embed()
            embed.set_footer(text=footer)
            messages.append(SimpleNamespace(author=SimpleNamespace(id=author), embeds=[embed], id=900,
                                            created_at=datetime.now(timezone.utc)))
        async def history(**kwargs):
            for message in messages:
                yield message
        channel = SimpleNamespace(guild=SimpleNamespace(id=1), history=history, send=AsyncMock())
        with self.assertRaises(DiscordFailure) as failure:
            await self.adapter(channel).notice({'guild_id': 1}, '30:1000', {'channel_id': 10}, recover=True)
        self.assertTrue(failure.exception.partial)
        channel.send.assert_not_awaited()

    async def test_recovery_permission_failure_keeps_uncertainty(self):
        async def history(**kwargs):
            raise discord.Forbidden(SimpleNamespace(status=403, reason='Forbidden'), 'No history access')
            yield
        channel = SimpleNamespace(guild=SimpleNamespace(id=1), history=history, send=AsyncMock())
        with self.assertRaises(DiscordFailure) as failure:
            await self.adapter(channel).notice({'guild_id': 1}, '30:1000', {'channel_id': 10}, recover=True)
        self.assertTrue(failure.exception.partial)
        channel.send.assert_not_awaited()

    async def test_ambiguous_notes_thread_is_not_adopted(self):
        matches = [SimpleNamespace(id=identity, name='staff-notes-7-1', parent_id=10, owner_id=99,
                                   is_private=lambda: True) for identity in (20, 21)]
        guild = SimpleNamespace(active_threads=AsyncMock(return_value=matches))
        adapter = DiscordTicketAdapter(SimpleNamespace(user=SimpleNamespace(id=99), get_guild=lambda _: guild))
        with self.assertRaises(DiscordFailure) as failure:
            await adapter.notes_thread({'id': 1, 'guild_id': 1, 'ticket_number': 7, 'discord_container_id': 10}, recover=True)
        self.assertTrue(failure.exception.partial)
