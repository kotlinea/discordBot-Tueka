import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,MagicMock
import discord
from discord_io import DiscordFailure
from starboard.discord_adapter import DiscordHighlightAdapter,failure


async def sequence(values):
    for value in values:yield value


class HighlightAdapterTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self,*,thread=False):
        target=MagicMock(spec=discord.Thread if thread else discord.TextChannel)
        target.guild=NS(id=1);target.id=11 if thread else 10
        target.is_nsfw.return_value=False
        if thread:target.parent=NS(id=10,is_nsfw=lambda:False);target.parent_id=10
        source=NS(author=NS(id=1,bot=False,display_name='Generated author'),content='Generated proof',attachments=[],reactions=[])
        target.fetch_message=AsyncMock(return_value=source)
        bot=NS(user=NS(id=99));adapter=DiscordHighlightAdapter(bot);adapter.channel=AsyncMock(return_value=target)
        return adapter,target,source

    async def test_normal_and_super_reactions_count_each_person_once_excluding_self_and_bots(self):
        adapter,target,source=self.adapter(thread=True)
        types=[]
        def users(*,limit,type):
            self.assertEqual(limit,5001);types.append(type)
            return sequence([NS(id=1,bot=False),NS(id=2,bot=False),NS(id=3,bot=True)] if type==discord.ReactionType.normal else [NS(id=2,bot=False),NS(id=4,bot=False)])
        source.reactions=[NS(emoji='⭐',users=users)]
        snapshot,count=await adapter.source(1,11,100,'⭐')
        self.assertEqual(count,2);self.assertEqual(snapshot['parent_channel_id'],10)
        self.assertEqual(types,[discord.ReactionType.normal,discord.ReactionType.burst])

    async def test_nsfw_sources_do_not_fetch_voters(self):
        adapter,target,source=self.adapter();target.is_nsfw.return_value=True
        source.reactions=[NS(emoji='⭐',users=lambda **_:self.fail('NSFW vote fetch'))]
        snapshot,count=await adapter.source(1,10,100,'⭐')
        self.assertTrue(snapshot['nsfw']);self.assertEqual(count,0)
        target.fetch_message.assert_not_awaited()

    async def test_marker_and_author_are_both_required_before_deleting(self):
        adapter,target,message=self.adapter();message.embeds=[NS(footer=NS(text='Generated marker'))];message.delete=AsyncMock()
        with self.assertRaises(DiscordFailure):await adapter.delete(1,10,100,'Generated marker')
        message.author.id=99
        with self.assertRaises(DiscordFailure):await adapter.delete(1,10,100,'Wrong marker')
        message.delete.assert_not_awaited()
        await adapter.delete(1,10,100,'Generated marker');message.delete.assert_awaited_once()

    async def test_receipt_scan_is_bounded_and_matches_only_owned_marker(self):
        adapter,target,_=self.adapter()
        messages=[NS(id=1,author=NS(id=2),embeds=[NS(footer=NS(text='proof'))]),NS(id=2,author=NS(id=99),embeds=[NS(footer=NS(text='other'))]),NS(id=3,author=NS(id=99),embeds=[NS(footer=NS(text='proof'))])]
        target.history=MagicMock(side_effect=lambda **_:sequence(messages))
        self.assertEqual(await adapter.reconcile(1,20,'proof'),3)
        target.history.assert_called_once_with(limit=200)

    async def test_request_failures_preserve_uncertainty_only_for_possible_sends(self):
        for status,retry,partial,missing in ((403,False,False,False),(404,False,False,True),(429,True,False,False),(500,True,True,False)):
            exc=discord.HTTPException(NS(status=status,reason='Generated'), 'Generated failure')
            result=failure(exc,send=True)
            self.assertEqual((result.retry,result.partial,result.missing),(retry,partial,missing))
        self.assertTrue(failure(TimeoutError(),send=True).partial)
        self.assertFalse(failure(TimeoutError()).partial)
