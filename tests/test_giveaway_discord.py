import datetime
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock
import discord
from db_support import prepare_database
from giveaways.discord_adapter import DiscordGiveawayAdapter, presentation, failure
from cogs.engagement.giveaways import GiveawaysCog
from jobs import Outcome
from discord_io import DiscordFailure


class GiveawayAdapterTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self):
        channel = MagicMock(spec=discord.TextChannel)
        channel.guild = NS(id=1)
        channel.id = 20
        guild = NS(id=1, get_channel=lambda _: channel, fetch_member=AsyncMock())
        bot = NS(user=NS(id=99), get_guild=lambda _: guild)
        return DiscordGiveawayAdapter(bot), channel, guild

    def plan(self):
        return {'campaign': {'id': 1, 'guild_id': 1, 'status': 'closed', 'ends_at': 1000, 'config': {'kind': 'giveaway', 'title': 'Generated', 'description': '', 'channel_id': 20, 'capacity': 3}},
                'entrants': 2, 'draw': {'round_number': 1, 'winners_json': '[30]'}}

    async def test_member_is_fetched_fresh_and_scope_checked(self):
        adapter, _, guild = self.adapter()
        member = NS(id=30, guild=NS(id=1), bot=False, roles=[NS(id=10)], created_at=datetime.datetime.fromtimestamp(0, datetime.UTC), joined_at=None)
        guild.fetch_member.return_value = member
        result = await adapter.member(1, 30)
        self.assertIsNone(result['joined_at'])
        self.assertEqual(result['role_ids'], [10])
        guild.fetch_member.assert_awaited_once_with(30)
        member.guild.id = 2
        with self.assertRaises(DiscordFailure):
            await adapter.member(1, 30)

    async def test_publication_has_safe_mentions_and_final_buttons_disabled(self):
        adapter, channel, _ = self.adapter()
        channel.send = AsyncMock(return_value=NS(id=100))
        self.assertEqual(await adapter.send(self.plan(), 'Tueka campaign:1'), 100)
        args = channel.send.call_args.kwargs
        self.assertFalse(args['allowed_mentions'].everyone)
        self.assertFalse(args['allowed_mentions'].users)
        self.assertTrue(all(button.disabled for button in args['view'].children))
        self.assertEqual(args['embed'].footer.text, 'Tueka campaign:1')

    async def test_edit_rejects_foreign_bot_and_marker_mismatch(self):
        adapter, channel, _ = self.adapter()
        message = NS(author=NS(id=98), embeds=[NS(footer=NS(text='Tueka campaign:1'))], edit=AsyncMock())
        channel.fetch_message = AsyncMock(return_value=message)
        with self.assertRaises(DiscordFailure):
            await adapter.edit(self.plan(), 100, 'Tueka campaign:1')
        message.author.id = 99
        message.embeds[0].footer.text = 'Different'
        with self.assertRaises(DiscordFailure):
            await adapter.edit(self.plan(), 100, 'Tueka campaign:1')
        message.edit.assert_not_awaited()

    async def test_expired_open_post_disables_entries_before_close_worker_runs(self):
        plan = self.plan()
        plan['campaign']['status'] = 'open'
        _, view = presentation(plan, 'marker', 1000)
        self.assertTrue(all(button.disabled for button in view.children))

    def test_send_failure_distinguishes_uncertain_from_definitive(self):
        for status, partial, retry in ((403, False, False), (429, False, True), (500, True, True)):
            exc = discord.HTTPException(NS(status=status, reason='Generated'), 'Generated')
            result = failure(exc, send=True)
            self.assertEqual(result.partial, partial)
            self.assertEqual(result.retry, retry)


class GiveawayGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.url = prepare_database(Path(self.tmp.name) / 'giveaway-gateway', self.addCleanup)
        self.cog = GiveawaysCog(NS(settings=NS(database_url=self.url)))
        self.repo = self.cog.repo
        self.repo.settings.set_module(1, 'giveaways', enabled=True)
        item = self.repo.create(1, 10, {'title': 'Generated', 'channel_id': 20, 'ends_at': int(time.time()) + 600}, 'generated')
        self.item = self.repo.launch(1, item['id'], 10, item['revision'])
        claim = self.repo.jobs.claim('publisher')
        self.repo.publication_begin(claim.payload)
        self.repo.publication_receipt(claim.payload, 100)
        self.repo.jobs.finish(claim, Outcome())
        self.port = NS(member=AsyncMock(return_value={'id': 30, 'guild_id': 1, 'bot': False, 'role_ids': [], 'created_at': 0, 'joined_at': 0}))
        self.cog.service.port = self.port

    def interaction(self, *, guild=1, message=100, custom=None, identity=1000):
        member = MagicMock(spec=discord.Member)
        member.id = 30
        return NS(type=discord.InteractionType.component, data={'custom_id': custom or f'tueka-campaign:{self.item["id"]}:join'},
                  guild=NS(id=guild), message=NS(id=message), user=member, id=identity,
                  response=NS(defer=AsyncMock()), followup=NS(send=AsyncMock()))

    async def test_gateway_join_and_duplicate_are_private_and_idempotent(self):
        interaction = self.interaction()
        await self.cog.on_interaction(interaction)
        await self.cog.on_interaction(interaction)
        self.assertEqual(len(self.repo.history(1, self.item['id'])['entries']), 1)
        self.assertTrue(interaction.followup.send.call_args.kwargs['ephemeral'])

    async def test_wrong_guild_receipt_and_off_do_not_fetch_members_or_write(self):
        for interaction in (self.interaction(guild=2), self.interaction(message=999)):
            await self.cog.on_interaction(interaction)
        self.repo.settings.set_module(1, 'giveaways', enabled=False)
        await self.cog.on_interaction(self.interaction())
        self.port.member.assert_not_awaited()
        self.assertEqual(self.repo.history(1, self.item['id'])['entries'], [])

    async def test_unrelated_components_are_ignored(self):
        interaction = self.interaction(custom='other:1:join')
        await self.cog.on_interaction(interaction)
        interaction.response.defer.assert_not_awaited()
