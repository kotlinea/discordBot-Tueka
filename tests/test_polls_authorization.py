"""Discord result entry points share current channel visibility requirements."""
from copy import deepcopy
from itertools import product
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, MagicMock

import discord

from cogs.engagement.advanced_polls import AdvancedPollsCog
from cogs.engagement.poll_results import ResultView
from engagement.polls.models import Actor, normalize


class PollChannelAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    entries=('show','details','page')

    def fixture(self, *, visible=True, manager=False):
        actor=Actor(1,20,(3,),manager=manager)
        member=NS(id=20)
        channel=MagicMock(spec=discord.TextChannel)
        channel.guild=NS(id=1)
        channel.permissions_for.return_value=NS(view_channel=visible)
        guild=NS(id=1,fetch_channel=AsyncMock(return_value=channel),fetch_member=AsyncMock(return_value=member))
        poll=dict(id=1,guild_id='1',channel_id='10',message_id='100',status='open',config=normalize(dict(question='Staff-only question',options=['A','B'])))
        cog=object.__new__(AdvancedPollsCog)
        cog.actor=AsyncMock(return_value=actor)
        cog.service=NS(read=Mock(return_value=deepcopy(poll)))
        cog.engagement_repository=NS(by_message=Mock(return_value=dict(id=1,guild_id=1)))
        interaction=NS(guild=guild,user=NS(id=20),channel=NS(id=99),message=NS(id=100),
            type=discord.InteractionType.component,data={'custom_id':'tueka-poll-details:100:0'},
            response=NS(is_done=Mock(return_value=False),defer=AsyncMock(),send_message=AsyncMock()),
            followup=NS(send=AsyncMock()),edit_original_response=AsyncMock())
        return cog,interaction,actor,channel,member

    async def invoke(self, entry, cog, interaction, actor):
        if entry=='show':
            await AdvancedPollsCog.poll_show.callback(cog,interaction,1)
        elif entry=='details':
            await cog.on_interaction(interaction)
        else:
            await ResultView(cog,actor,1).update(interaction)

    def embeds(self, interaction):
        calls=interaction.response.send_message.call_args_list+interaction.followup.send.call_args_list+interaction.edit_original_response.call_args_list
        return [call.kwargs['embed'] for call in calls if 'embed' in call.kwargs]

    async def test_visibility_matrix_across_result_entry_points(self):
        for entry,manager,visible in product(self.entries,(False,True),(False,True)):
            with self.subTest(entry=entry,manager=manager,visible=visible):
                cog,i,actor,channel,member=self.fixture(visible=visible,manager=manager)
                await self.invoke(entry,cog,i,actor)
                self.assertEqual(bool(self.embeds(i)),visible)
                if visible:self.assertIn('Staff-only question',self.embeds(i)[0].description)
                i.guild.fetch_channel.assert_awaited_with(10)
                channel.permissions_for.assert_called_with(member)

    async def test_unavailable_or_foreign_channel_never_discloses_results(self):
        for entry,case in product(self.entries,('forbidden','missing','unavailable','foreign')):
            with self.subTest(entry=entry,case=case):
                cog,i,actor,channel,_=self.fixture()
                if case=='foreign':channel.guild.id=2
                else:
                    status={'forbidden':403,'missing':404,'unavailable':503}[case]
                    i.guild.fetch_channel.side_effect=discord.HTTPException(NS(status=status,reason='unavailable'),'generated failure')
                await self.invoke(entry,cog,i,actor)
                self.assertEqual(self.embeds(i),[])

    async def test_result_pagination_rechecks_revoked_visibility(self):
        cog,i,actor,channel,_=self.fixture()
        view=ResultView(cog,actor,1)
        await view.update(i)
        self.assertEqual(len(self.embeds(i)),1)
        channel.permissions_for.return_value.view_channel=False
        await view.update(i)
        self.assertEqual(len(self.embeds(i)),1)
        self.assertEqual(i.guild.fetch_channel.await_count,2)

    async def test_private_thread_requires_membership_or_manage_threads(self):
        for entry,manager,joined in product(self.entries,(False,True),(False,True)):
            with self.subTest(entry=entry,manage_threads=manager,joined=joined):
                cog,i,actor,_,_=self.fixture()
                thread=MagicMock(spec=discord.Thread)
                thread.guild=NS(id=1)
                thread.is_private.return_value=True
                thread.permissions_for.return_value=NS(view_channel=True,manage_threads=manager)
                thread.fetch_member=AsyncMock(return_value=NS(id=20))
                if not joined:thread.fetch_member.side_effect=discord.NotFound(NS(status=404,reason='not joined'),'generated failure')
                i.guild.fetch_channel.return_value=thread
                await self.invoke(entry,cog,i,actor)
                self.assertEqual(bool(self.embeds(i)),manager or joined)
