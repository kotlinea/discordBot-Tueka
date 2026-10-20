"""Ticket admission, permission and delivery boundary regressions."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import discord
from cryptography.fernet import Fernet
from db_support import prepare_database
from ticketing import TicketRepository, TicketService, TranscriptStorage, TicketValidationError
from ticketing.models import validate_panel
from ticketing.messages import welcome
from ticketing.discord_adapter import DiscordTicketAdapter
from cogs.community.tickets import TicketsCog


class TicketReview(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.repo = TicketRepository(prepare_database(root / 'test', self.addCleanup))
        self.storage = TranscriptStorage(root / 'blobs', Fernet.generate_key().decode())
        self.service = TicketService(self.repo, self.storage)
        self.repo.save_settings(1, {'enabled': True, 'open_limit': 10})
        self.team = self.repo.save_team(1, {'name': 'Staff', 'role_ids': [500]})
        self.panel = self.repo.save_panel(1, {'name': 'Support', 'mode': 'channel', 'category_id': 100, 'team_id': self.team['id']})

    def opened(self):
        ticket, _ = self.service.reserve(1, self.panel['id'], 10, self.id(), set())
        return self.repo.activate_ticket(ticket['id'], 700, 100)

    async def test_notification_join_is_rejected_before_staff_check(self):
        self.panel = self.repo.save_panel(1, {**self.panel, 'mode': 'private_thread', 'thread_parent_channel_id': 801, 'staff_notification_channel_id': 800}, self.panel['id'])
        ticket = self.opened()
        self.repo.finish_notice(ticket, 'notify', {'id': 900, 'created_at': 1000})
        interaction = SimpleNamespace(type=discord.InteractionType.component,
            data={'custom_id': f"tueka-ticket:join:{ticket['id']}"}, guild=SimpleNamespace(id=1),
            channel_id=800, message=SimpleNamespace(id=900), user=Mock(spec=discord.Member),
            response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()))
        cog = SimpleNamespace(repository=self.repo, _staff=AsyncMock(return_value=True))
        interaction.user.id = 20
        await TicketsCog.on_interaction(cog, interaction)
        self.assertTrue(any(row['action'] == 'participant_add' for row in self.repo.outbox(ticket['id'])), 'Valid staff notification Join must queue participant_add')
        cog._staff.assert_awaited_once()

    async def test_accepted_reply_exceeds_discord_content_budget(self):
        ticket = self.opened()
        item = self.service.queue_reply(ticket['id'], 20, 'Staff', 'x' * 2000)
        port = SimpleNamespace(send_reply=AsyncMock(return_value={'id': 900, 'created_at': 1000}))
        await self.service.deliver_message(port, ticket, item)
        sent = port.send_reply.await_args.args[2]
        channel = Mock(spec=discord.TextChannel)
        channel.guild = SimpleNamespace(id=1)
        channel.send = AsyncMock(return_value=SimpleNamespace(id=901, created_at=datetime.now(timezone.utc)))
        guild = SimpleNamespace(id=1, get_channel_or_thread=lambda _: channel)
        adapter = DiscordTicketAdapter(SimpleNamespace(get_guild=lambda _: guild))
        await adapter.send_reply(ticket, 'reply-budget', sent, recover=False)
        payload = channel.send.await_args.kwargs
        self.assertLessEqual(len(payload.get('content') or ''), 2000)
        self.assertIn('x' * 2000, (payload.get('content') or '') + (payload['embed'].description or ''))

    async def test_disable_between_validation_and_reservation_is_ignored(self):
        original = self.repo.reserve_ticket
        def disable_then_reserve(*args, **kwargs):
            self.repo.save_settings(1, {'enabled': False, 'open_limit': 10})
            return original(*args, **kwargs)
        with patch.object(self.repo, 'reserve_ticket', side_effect=disable_then_reserve):
            with self.assertRaises(TicketValidationError, msg='Disabled intake must reject reservation after disabled setting commits'):
                self.service.reserve(1, self.panel['id'], 10, self.id(), set())
        self.assertFalse(self.repo.settings(1)['enabled'])

    async def test_welcome_adds_form_fields_beyond_validated_embed_limit(self):
        fields = [{'name': f'f{i}', 'value': 'v'} for i in range(25)]
        panel = validate_panel({**self.panel, 'welcome_embed': {'fields': fields}})
        packet = welcome(self.opened(), panel, {'id': 10, 'name': 'Member'}, self.team, {'answer': 'value'})
        self.assertLessEqual(len(packet['embed']['fields']), 25)

    async def test_oncall_survives_team_removal_and_is_added_to_private_ticket(self):
        self.repo.set_on_call(1, self.team['id'], 20, True)
        self.repo.save_team(1, {'name': 'Staff', 'role_ids': []}, self.team['id'])
        panel = {**self.panel, 'mode': 'private_thread', 'thread_parent_channel_id': 800}
        thread = SimpleNamespace(id=700, parent_id=800, add_user=AsyncMock())
        parent = Mock(spec=discord.TextChannel)
        parent.create_thread = AsyncMock(return_value=thread)
        opener, former_staff = SimpleNamespace(id=10), SimpleNamespace(id=20, roles=[])
        guild = SimpleNamespace(id=1, me=SimpleNamespace(id=99), get_channel=lambda _: parent,
            get_member=lambda user: {10: opener, 20: former_staff}.get(user))
        adapter = DiscordTicketAdapter(SimpleNamespace(get_guild=lambda _: guild))
        await adapter.create_container({'guild_id': 1, 'opener_id': 10, 'id': 1}, panel, 'ticket', [], self.repo.on_call_members(1, self.team['id']))
        self.assertNotIn(former_staff, [call.args[0] for call in thread.add_user.await_args_list])

    async def test_definitely_unsent_panel_retry_is_trapped_in_receipt_recovery(self):
        from ticketing.panel_delivery import PanelDeliveryService
        from discord_io import DiscordFailure
        config = self.repo.save_panel_message(1, {'name': 'Support', 'channel_id': 800, 'title': 'Support', 'panel_ids': [self.panel['id']]})
        class Port:
            def __init__(self):
                self.recovery_flags = []
            async def publish_panel(self, config, panels, *, recover):
                self.recovery_flags.append(recover)
                if len(self.recovery_flags) == 1:
                    raise DiscordFailure('channel cache temporarily unavailable', retry=True, partial=False)
                if recover:
                    raise DiscordFailure('No receipt exists because first send never happened', partial=True)
                return 900
        port = Port()
        delivery = PanelDeliveryService(self.repo, port)
        await delivery.deliver(self.repo.claim_panel_messages('worker')[0])
        await delivery.deliver(self.repo.claim_panel_messages('worker')[0])
        self.assertEqual(port.recovery_flags, [False, False])
        self.assertEqual(self.repo.panel_message(1, config['id'])['status'], 'published')
    async def test_valid_guild_custom_emoji_is_accepted(self):
        from dashboard.api.community.ticket_support.resources import TicketResources
        resources = SimpleNamespace(channels={}, role_ids=set(), missing_permissions=lambda _: set())
        discord_api = SimpleNamespace(guild_emojis=AsyncMock(return_value=[{'id': '123456789012345678'}]))
        value = {'panel': {'button': {'emoji': '<:valid:123456789012345678>'}}, 'deployment': {}}
        with patch('dashboard.api.community.ticket_support.resources.GuildResources.fetch', AsyncMock(return_value=resources)):
            await TicketResources(discord_api).validate_ticket_bundle_resources(1, value)
    async def test_competing_claim_is_fenced_by_resource_lease(self):
        from discord_io import DiscordFailure
        ticket = self.opened()
        entered, release = asyncio.Event(), asyncio.Event()
        class Port:
            async def claim_changes(self, *args):
                entered.set()
                await release.wait()
                return []
            async def permission(self, *args, **kwargs):
                raise AssertionError('no permission changes')
        port = Port()
        first = asyncio.create_task(self.service.change_claim(port, ticket, self.panel, 20, ticket['revision']))
        await asyncio.wait_for(entered.wait(), 10)
        try:
            with self.assertRaises(DiscordFailure):
                await self.service.change_claim(port, ticket, self.panel, 30, ticket['revision'])
        finally:
            release.set()
        saved = await first
        self.assertEqual(saved['claimed_by'], 20)
        self.assertEqual(self.repo.pending_claim_changes(1), [])

    async def test_competing_open_does_not_duplicate_resource(self):
        from discord_io import DiscordFailure
        from ticketing.contracts import ContainerRef
        ticket, panel = self.service.reserve(1, self.panel['id'], 10, self.id(), set())
        entered, release = asyncio.Event(), asyncio.Event()
        class Port:
            calls = 0
            async def create_container(self, *args):
                self.calls += 1
                entered.set()
                await release.wait()
                return ContainerRef(700, 100)
        port = Port()
        first = asyncio.create_task(self.service.open_container(port, ticket, panel, 'ticket'))
        await asyncio.wait_for(entered.wait(), 10)
        try:
            with self.assertRaises(DiscordFailure):
                await self.service.open_container(port, ticket, panel, 'ticket')
        finally:
            release.set()
        saved, _ = await first
        self.assertEqual(port.calls, 1)
        self.assertEqual(saved['status'], 'open')
    async def test_notification_join_rejects_wrong_guild_channel_receipt_or_staff(self):
        self.panel = self.repo.save_panel(1, {**self.panel, 'mode': 'private_thread', 'thread_parent_channel_id': 801, 'staff_notification_channel_id': 800}, self.panel['id'])
        ticket = self.opened()
        self.repo.finish_notice(ticket, 'notify', {'id': 900, 'created_at': 1000})
        for guild_id, channel_id, message_id, staff in ((2, 800, 900, True), (1, 802, 900, True), (1, 800, 901, True), (1, 800, 900, False)):
            with self.subTest(guild=guild_id, channel=channel_id, receipt=message_id, staff=staff):
                interaction = SimpleNamespace(type=discord.InteractionType.component,
                    data={'custom_id': f"tueka-ticket:join:{ticket['id']}"}, guild=SimpleNamespace(id=guild_id),
                    channel_id=channel_id, message=SimpleNamespace(id=message_id), user=Mock(spec=discord.Member),
                    response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock()), followup=SimpleNamespace(send=AsyncMock()))
                cog = SimpleNamespace(repository=self.repo, _staff=AsyncMock(return_value=staff))
                interaction.user.id = 20
                await TicketsCog.on_interaction(cog, interaction)
                self.assertFalse(any(row['action'] == 'participant_add' for row in self.repo.outbox(ticket['id'])))

    async def test_reply_payload_lengths_and_recovery_keep_full_body(self):
        ticket = self.opened()
        for size in (1, 1880, 1999, 2000):
            for anonymous in (False, True):
                with self.subTest(size=size, anonymous=anonymous):
                    channel = Mock(spec=discord.TextChannel)
                    channel.guild = SimpleNamespace(id=1)
                    channel.send = AsyncMock(return_value=SimpleNamespace(id=901, created_at=datetime.now(timezone.utc)))
                    guild = SimpleNamespace(id=1, get_channel_or_thread=lambda _: channel)
                    adapter = DiscordTicketAdapter(SimpleNamespace(get_guild=lambda _: guild))
                    item = self.service.queue_reply(ticket['id'], 20, 'S' * 100, 'x' * size, anonymous=anonymous)
                    await self.service.deliver_message(adapter, ticket, item)
                    payload = channel.send.await_args.kwargs
                    self.assertLessEqual(len(payload.get('content') or ''), 2000)
                    self.assertLessEqual(len(payload['embed'].description or ''), 4096)
                    self.assertIn('x' * size, (payload.get('content') or '') + (payload['embed'].description or ''))
                    self.assertTrue(payload['embed'].footer.text.startswith('Tueka ticket delivery:'))
        with self.assertRaises(TicketValidationError):
            self.service.queue_reply(ticket['id'], 20, 'Staff', 'x' * 2001)

    async def test_completed_welcome_embed_budget_includes_receipt(self):
        fields = [{'name': '{username}' * 20, 'value': '{panel}' * 100} for _ in range(3)]
        panel = validate_panel({**self.panel, 'name': 'P' * 80, 'welcome_embed': {'title': '{username}' * 20,
            'description': '{panel}' * 200, 'footer': {'enabled': True, 'text': 'f' * 500}, 'fields': fields}})
        ticket = self.opened()
        packet = welcome(ticket, panel, {'id': 10, 'name': 'M' * 32}, self.team, {f'answer{i}': 'a' * 1024 for i in range(5)})
        channel = SimpleNamespace(guild=SimpleNamespace(id=1), send=AsyncMock(return_value=SimpleNamespace(id=901, created_at=datetime.now(timezone.utc))))
        guild = SimpleNamespace(id=1, get_channel_or_thread=lambda _: channel)
        adapter = DiscordTicketAdapter(SimpleNamespace(get_guild=lambda _: guild))
        await adapter.notice(ticket, '123:1000', packet, recover=False)
        embed = channel.send.await_args.kwargs['embed']
        self.assertLessEqual(len(embed), 6000)
        self.assertLessEqual(len(embed.fields), 25)
        self.assertLessEqual(len(embed.title or ''), 256)
        self.assertLessEqual(len(embed.description or ''), 4096)
        self.assertLessEqual(len(embed.footer.text or ''), 2048)
        self.assertTrue(embed.footer.text.endswith('Tueka ticket notice:123:1000'))
        for field in embed.fields:
            self.assertTrue(1 <= len(field.name) <= 256)
            self.assertTrue(1 <= len(field.value) <= 1024)

    async def test_oncall_keeps_current_role_and_explicit_team_users(self):
        from ticketing.contracts import ContainerRef
        team = self.repo.save_team(1, {'name': 'Staff', 'role_ids': [500], 'user_ids': [21], 'admin_user_ids': [22]}, self.team['id'])
        for user_id in (20, 21, 22, 23):
            self.repo.set_on_call(1, team['id'], user_id, True)
        panel = self.repo.save_panel(1, {**self.panel, 'mode': 'private_thread', 'thread_parent_channel_id': 800, 'staff_notification_channel_id': 801}, self.panel['id'])
        ticket, panel = self.service.reserve(1, panel['id'], 10, self.id(), set())
        thread = SimpleNamespace(id=700, parent_id=800, add_user=AsyncMock())
        parent = Mock(spec=discord.TextChannel)
        parent.create_thread = AsyncMock(return_value=thread)
        members = {user_id: SimpleNamespace(id=user_id, roles=[SimpleNamespace(id=500)] if user_id == 20 else []) for user_id in (10, 20, 21, 22, 23)}
        guild = SimpleNamespace(id=1, me=SimpleNamespace(id=99), get_channel=lambda _: parent, get_member=lambda user: members.get(user))
        adapter = DiscordTicketAdapter(SimpleNamespace(get_guild=lambda _: guild))
        await self.service.open_container(adapter, ticket, panel, 'ticket')
        added = [call.args[0].id for call in thread.add_user.await_args_list]
        self.assertEqual(added, [10, 20, 21, 22])
        self.assertEqual(self.repo.on_call_members(2, team['id']), [])

    async def test_disabled_intake_preserves_existing_reservation_and_other_guild(self):
        from ticketing.contracts import ContainerRef
        ticket, panel = self.service.reserve(1, self.panel['id'], 10, self.id(), set())
        self.repo.save_settings(1, {'enabled': False})
        same = self.repo.reserve_ticket(1, panel['id'], 10, self.id(), {})
        self.assertEqual(same['id'], ticket['id'])
        port = SimpleNamespace(create_container=AsyncMock(return_value=ContainerRef(700, 100)))
        opened, _ = await self.service.open_container(port, ticket, panel, 'ticket')
        self.assertEqual(opened['status'], 'open')
        with self.assertRaises(TicketValidationError):
            self.service.reserve(1, panel['id'], 11, self.id() + '-new', set())
        self.repo.save_settings(2, {'enabled': True, 'open_limit': 10})
        team2 = self.repo.save_team(2, {'name': 'Staff'})
        panel2 = self.repo.save_panel(2, {'name': 'Other', 'team_id': team2['id'], 'category_id': 100})
        other, _ = self.service.reserve(2, panel2['id'], 11, self.id() + '-other', set())
        self.assertEqual(other['guild_id'], 2)

    async def test_unknown_panel_result_only_reconciles_without_resending(self):
        from ticketing.panel_delivery import PanelDeliveryService
        from discord_io import DiscordFailure
        config = self.repo.save_panel_message(1, {'name': 'Support', 'channel_id': 800, 'title': 'Support', 'panel_ids': [self.panel['id']]})
        class Port:
            def __init__(self):
                self.flags = []
            async def publish_panel(self, config, panels, *, recover):
                self.flags.append(recover)
                raise DiscordFailure('unknown receipt', retry=True, partial=True)
        port = Port()
        delivery = PanelDeliveryService(self.repo, port)
        await delivery.deliver(self.repo.claim_panel_messages('worker')[0])
        await delivery.deliver(self.repo.claim_panel_messages('worker')[0])
        self.assertEqual(port.flags, [False, True])
        self.assertEqual(self.repo.panel_message(1, config['id'])['status'], 'publishing')
if __name__ == '__main__':
    unittest.main(verbosity=2)










