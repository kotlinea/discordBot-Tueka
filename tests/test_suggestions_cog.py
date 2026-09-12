from db_support import prepare_database
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
from cogs.suggestions import SuggestionsCog


class SuggestionsCogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bot = SimpleNamespace(settings=SimpleNamespace(database_path=prepare_database(Path(self.temp.name) / 'test.db')))
        self.cog = SuggestionsCog(self.bot)
        self.cog.storage.set_module(1, 'suggestions', enabled=True, settings={'channel_id': 10, 'review_role_ids': [40]})
        self.channel = MagicMock(spec=discord.TextChannel)
        self.channel.id = 10
        self.channel.send = AsyncMock(return_value=SimpleNamespace(id=100))
        self.guild = SimpleNamespace(id=1, get_channel=lambda _: self.channel)

    def interaction(self, custom_id=''):
        user = MagicMock(spec=discord.Member)
        user.id = 20
        user.guild_permissions = discord.Permissions.none()
        user.roles = []
        return SimpleNamespace(
            guild=self.guild, user=user, message=SimpleNamespace(id=100),
            type=discord.InteractionType.component, data={'custom_id': custom_id},
            response=SimpleNamespace(send_message=AsyncMock(), edit_message=AsyncMock(), defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
        )

    def item(self):
        value = self.cog.repository.create(1, 10, 20, {'idea': 'Idea'})
        return self.cog.repository.attach_message(1, value['id'], 100)

    async def test_submit_and_delivery_failure(self):
        interaction = self.interaction()
        await self.cog.submit_modal(interaction, {}, {'idea': 'Idea'})
        self.assertEqual(self.cog.repository.list(1)[0]['message_id'], 100)
        self.channel.send.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason='Forbidden'), 'Denied')
        await self.cog.submit_modal(self.interaction(), {}, {'idea': 'Another'})
        self.assertEqual(self.cog.repository.list(1)[0]['status'], 'delivery_failed')

    async def test_disabled_blocks_submit_and_existing_buttons(self):
        item = self.item()
        self.cog.storage.set_module(1, 'suggestions', enabled=False)
        await self.cog.submit_modal(self.interaction(), {}, {'idea': 'Ignored'})
        await self.cog.on_interaction(self.interaction(f"tueka-suggestion:vote:{item['id']}:up"))
        self.channel.send.assert_not_awaited()
        self.assertEqual(len(self.cog.repository.list(1)), 1)
        self.assertEqual(self.cog.repository.get(1, item['id'])['upvotes'], 0)

    async def test_recreated_cog_handles_existing_button(self):
        item = self.item()
        restarted = SuggestionsCog(self.bot)
        interaction = self.interaction(f"tueka-suggestion:vote:{item['id']}:up")
        await restarted.on_interaction(interaction)
        self.assertEqual(restarted.repository.get(1, item['id'])['upvotes'], 1)
        interaction.response.edit_message.assert_awaited_once()

    async def test_review_requires_staff_role_or_manage_messages(self):
        item = self.item()
        interaction = self.interaction(f"tueka-suggestion:review:{item['id']}:approved")
        await self.cog.on_interaction(interaction)
        self.assertEqual(self.cog.repository.get(1, item['id'])['status'], 'pending')
        interaction.user.roles = [SimpleNamespace(id=40)]
        await self.cog.on_interaction(interaction)
        self.assertEqual(self.cog.repository.get(1, item['id'])['status'], 'approved')
        interaction.user.roles = []
        interaction.user.guild_permissions = discord.Permissions(manage_messages=True)
        self.assertTrue(self.cog._can_review(interaction, self.cog._settings(1)))

    async def test_other_guild_and_message_cannot_vote(self):
        item = self.item()
        interaction = self.interaction(f"tueka-suggestion:vote:{item['id']}:up")
        interaction.message.id = 101
        await self.cog.on_interaction(interaction)
        self.cog.storage.set_module(2, 'suggestions', enabled=True, settings={'channel_id': 10})
        interaction.guild = SimpleNamespace(id=2)
        interaction.message.id = 100
        await self.cog.on_interaction(interaction)
        self.assertEqual(self.cog.repository.get(1, item['id'])['upvotes'], 0)
        interaction.response.edit_message.assert_not_awaited()
