import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,MagicMock
import discord
from db_support import prepare_database
from database import transaction
from discord_io import DiscordFailure
from jobs import run_batch
from cogs.engagement.starboard import StarboardCog


class StarboardGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.url=prepare_database(Path(self.tmp.name)/'starboard-gateway',self.addCleanup)
        self.channel=MagicMock(spec=discord.TextChannel);self.channel.id=10;self.channel.guild=NS(id=1)
        guild=NS(get_channel_or_thread=lambda channel:self.channel if channel==10 else None)
        self.bot=NS(settings=NS(database_url=self.url),get_guild=lambda guild_id:guild if guild_id==1 else None)
        self.cog=StarboardCog(self.bot);self.repo=self.cog.repository;self.now=int(time.time())
        self.repo.clock=lambda:self.now;self.repo.jobs.clock=lambda:self.now;self.repo.refresh_jobs.clock=lambda:self.now
        self.repo.settings.set_module(1,'starboard',enabled=True,settings={})
        self.board=self.repo.save_board(1,30,{'name':'Generated board','enabled':True,'target_channel_id':20,'source_channel_ids':[10],'threshold':2})
        self.source={'guild_id':1,'channel_id':10,'message_id':100,'author_id':40,'author_bot':False,'content':'Generated gateway proof'}
        self.cog.adapter.channel=AsyncMock(return_value=self.channel)
        self.cog.adapter.source=AsyncMock(return_value=(self.source,2))
        self.payload=NS(guild_id=1,channel_id=10,message_id=100,emoji=discord.PartialEmoji(name='⭐'))

    async def test_raw_event_persists_before_fetch_and_429_retries_without_losing_initial_highlight(self):
        await self.cog.on_raw_reaction_add(self.payload)
        self.cog.adapter.source.assert_not_awaited()
        self.cog.adapter.source.side_effect=DiscordFailure('Generated 429',retry=True)
        self.assertEqual(await run_batch(self.repo.refresh_jobs,'generated',self.cog.refresh_job,limit=1),1)
        self.assertEqual(self.repo.entries(1,self.board['id']),[])
        self.now+=100;self.cog.adapter.source.side_effect=None
        self.assertEqual(await run_batch(self.repo.refresh_jobs,'generated',self.cog.refresh_job,limit=1),1)
        self.assertEqual(len(self.repo.entries(1,self.board['id'])),1)

    async def test_unrelated_reaction_and_channel_do_not_queue_or_read_message_content(self):
        await self.cog.on_raw_reaction_add(NS(**{**vars(self.payload),'emoji':discord.PartialEmoji(name='👍')}))
        other=MagicMock(spec=discord.TextChannel);other.id=99
        self.bot.get_guild=lambda _:NS(get_channel_or_thread=lambda _:other)
        await self.cog.on_raw_reaction_add(NS(**{**vars(self.payload),'channel_id':99}))
        self.assertIsNone(self.repo.refresh_jobs.claim('generated'))
        self.cog.adapter.source.assert_not_awaited();self.cog.adapter.channel.assert_not_awaited()

    async def test_missing_channel_withdraws_known_source_without_fetching_content(self):
        self.repo.observe(1,self.board['id'],1,self.source,2)
        await self.cog.on_raw_message_edit(self.payload)
        self.cog.adapter.channel.side_effect=DiscordFailure('Generated missing source channel',missing=True)
        await run_batch(self.repo.refresh_jobs,'generated',self.cog.refresh_job,limit=1)
        self.cog.adapter.source.assert_not_awaited()
        source=self.repo.entries(1,self.board['id'])[0]['snapshot']
        self.assertTrue(source['deleted']);self.assertEqual(source['content'],'')

    async def test_bulk_delete_while_off_keeps_tombstones_and_does_not_consume_attempts(self):
        self.repo.observe(1,self.board['id'],1,self.source,2)
        self.repo.settings.set_module(1,'starboard',enabled=False)
        await self.cog.on_raw_bulk_message_delete(NS(guild_id=1,channel_id=10,message_ids={100,101}))
        self.assertTrue(self.repo.entries(1,self.board['id'])[0]['snapshot']['deleted'])
        self.assertIsNone(self.repo.jobs.claim('paused'))
        with transaction(self.url) as c:self.assertEqual(c.execute('SELECT attempts FROM starboard_outbox').fetchone()['attempts'],0)
        self.repo.settings.set_module(1,'starboard',enabled=True)
        self.assertIsNotNone(self.repo.jobs.claim('resumed'))

    async def test_marking_parent_nsfw_removes_stored_body_without_source_reads(self):
        self.repo.observe(1,self.board['id'],1,{**self.source,'channel_id':11,'parent_channel_id':10},2)
        await self.cog.on_guild_channel_update(NS(is_nsfw=lambda:False),NS(id=10,guild=NS(id=1),is_nsfw=lambda:True))
        source=self.repo.entries(1,self.board['id'])[0]['snapshot']
        self.assertEqual(source['content'],'');self.assertTrue(source['deleted'])
        self.cog.adapter.source.assert_not_awaited()
