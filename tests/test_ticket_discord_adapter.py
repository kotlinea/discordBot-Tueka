import unittest
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
from cryptography.fernet import Fernet

from cogs.community.tickets import TicketsCog
from db_support import prepare_database
from discord_io import DiscordFailure
from ticketing import TicketRepository, TicketService, TranscriptStorage
from ticketing.discord_adapter import DiscordTicketAdapter


class TicketDiscordAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_ticket_keeps_member_roles_and_form_answers_separate(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        repository = TicketRepository(prepare_database(root / 'tickets.db', self.addCleanup))
        storage = TranscriptStorage(root / 'blobs', Fernet.generate_key().decode())
        repository.save_settings(1, {'enabled': True, 'open_limit': 1})
        team = repository.save_team(1, {'name': 'Support', 'role_ids': [500]})
        form = repository.save_form(1, {'name': 'Contact', 'title': 'Contact', 'fields': [
            {'key': 'question', 'label': 'Question', 'style': 'short', 'required': True,
             'placeholder': '', 'min_length': 1, 'max_length': 100}]})
        panel = repository.save_panel(1, {'name': 'Support', 'mode': 'channel', 'category_id': 100,
            'team_id': team['id'], 'form_id': form['id'], 'required_role_ids': [500]})
        service = TicketService(repository, storage)
        service.open_container = AsyncMock(side_effect=lambda port, ticket, panel, name:
            (ticket, SimpleNamespace(id=700)))
        cog = SimpleNamespace(repository=repository, transcripts=storage, service=service,
            _staff=AsyncMock(return_value=False),
            discord=SimpleNamespace(container=lambda identifier: SimpleNamespace(mention='#ticket')))
        member = Mock(spec=discord.Member)
        member.id, member.name, member.roles = 10, 'Member', []
        interaction = SimpleNamespace(guild=SimpleNamespace(id=1), user=member, id=123,
            response=SimpleNamespace(is_done=lambda: False, defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()))
        answers = {'question': 'Generated recovery question'}
        await TicketsCog.create_ticket(cog, interaction, panel['id'], answers)
        service.open_container.assert_not_awaited()
        self.assertEqual(repository.tickets(1), [])
        member.roles = [SimpleNamespace(id=500)]
        interaction.id = 124
        await TicketsCog.create_ticket(cog, interaction, panel['id'], answers)
        service.open_container.assert_awaited_once()
        reserved = service.open_container.await_args.args[1]
        self.assertEqual(reserved['opener_id'], member.id)
        self.assertEqual(storage.decrypt_text(reserved['form_answers']['question']), answers['question'])
        self.assertNotEqual(reserved['form_answers']['question'], answers['question'])
        interaction.followup.send.assert_awaited_with('Ticketを作成しました: #ticket', ephemeral=True)

    def adapter(self, channel):
        guild = SimpleNamespace(id=1, get_channel_or_thread=lambda _: channel)
        bot = SimpleNamespace(user=SimpleNamespace(id=99), get_guild=lambda _: guild)
        return DiscordTicketAdapter(bot)

    async def test_attachment_falls_back_when_cache_is_missing_or_unsupported(self):
        for status in (404, 415):
            with self.subTest(status=status):
                error = discord.HTTPException(SimpleNamespace(status=status, reason='cache unavailable'), 'cache unavailable')
                attachment = SimpleNamespace(read=AsyncMock(side_effect=[error, b'generated attachment']))
                self.assertEqual(await self.adapter(None).read_attachment(attachment), b'generated attachment')
                self.assertEqual(attachment.read.await_args_list[0].kwargs, {'use_cached': True})
                self.assertEqual(attachment.read.await_args_list[1].kwargs, {'use_cached': False})

    async def test_attachment_does_not_fallback_on_auth_or_rate_limit_failure(self):
        for status in (403, 429, 503):
            with self.subTest(status=status):
                error = discord.HTTPException(SimpleNamespace(status=status, reason='request failed'), 'request failed')
                attachment = SimpleNamespace(read=AsyncMock(side_effect=error))
                with self.assertRaises(DiscordFailure) as raised:
                    await self.adapter(None).read_attachment(attachment)
                self.assertEqual(raised.exception.retry, status in (429, 503))
                attachment.read.assert_awaited_once_with(use_cached=True)

    async def test_attachment_fallback_preserves_source_retry_status(self):
        cached = discord.HTTPException(SimpleNamespace(status=415, reason='unsupported'), 'unsupported')
        source = discord.HTTPException(SimpleNamespace(status=503, reason='unavailable'), 'unavailable')
        attachment = SimpleNamespace(read=AsyncMock(side_effect=[cached, source]))
        with self.assertRaises(DiscordFailure) as raised:
            await self.adapter(None).read_attachment(attachment)
        self.assertTrue(raised.exception.retry)
        self.assertIs(raised.exception.__cause__, source)

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
