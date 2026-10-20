"""Poll display ordering, durable retry and Thread delivery boundaries."""
import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from cogs.engagement.advanced_polls import AdvancedPollsCog
from database import transaction
from database.migrations import MIGRATIONS, apply
from database.testing import temporary_database
from engagement import EngagementRepository


class PollDisplayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        context = temporary_database()
        self.url = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.repo = EngagementRepository(self.url)
        self.repo.create_poll(100, 1, 10, 20, 'Question', ['A', 'B'], None, None)
        self.message = NS(id=100, embed=AdvancedPollsCog._embed('Question', ['A', 'B']),
                          view=AdvancedPollsCog._view(100, ['A', 'B']))
        async def edit(**kwargs): self.message.__dict__.update(kwargs)
        self.apply_edit = edit
        self.message.edit = edit
        self.channel = MagicMock(spec=discord.TextChannel)
        self.channel.fetch_message = AsyncMock(return_value=self.message)
        self.guild = NS(id=1, get_channel=lambda _: self.channel,
                        get_channel_or_thread=lambda _: self.channel)
        self.cog = object.__new__(AdvancedPollsCog)
        self.cog.engagement_repository = self.repo
        self.cog.guild_settings = NS(module_enabled=lambda *args: True)
        self.cog.bot = NS(get_guild=lambda _: self.guild)
        self.cog._poll_locks = {}

    def interaction(self, user, option):
        return NS(type=discord.InteractionType.component, message=self.message,
                  guild=self.guild, user=NS(id=user),
                  data={'custom_id': f'tueka-poll:100:{option}'},
                  response=NS(edit_message=self.message.edit, defer=AsyncMock(), send_message=AsyncMock()))

    def expire(self):
        with transaction(self.url) as c:
            c.execute('UPDATE polls SET closes_at=1 WHERE message_id=100')

    async def close(self):
        await AdvancedPollsCog.close_expired_polls.coro(self.cog)

    def delay_first_edit(self):
        entered, release = asyncio.Event(), asyncio.Event()
        calls = 0
        async def edit(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                entered.set()
                await release.wait()
            await self.apply_edit(**kwargs)
        self.message.edit = edit
        return entered, release

    async def test_concurrent_votes_finish_with_latest_counts(self):
        entered, release = self.delay_first_edit()
        second_committed = asyncio.Event()
        cast = self.repo.cast_poll_vote
        def track(message, user, option):
            result = cast(message, user, option)
            if user == 31: second_committed.set()
            return result
        self.repo.cast_poll_vote = track
        first = asyncio.create_task(self.cog.on_interaction(self.interaction(30, 0)))
        await asyncio.wait_for(entered.wait(), 5)
        second = asyncio.create_task(self.cog.on_interaction(self.interaction(31, 1)))
        await asyncio.wait_for(second_committed.wait(), 5)
        release.set()
        await asyncio.gather(first, second)
        self.assertIn('1. A — **1**票', self.message.embed.fields[0].value)
        self.assertIn('2. B — **1**票', self.message.embed.fields[0].value)

    async def test_close_cannot_be_overwritten_by_inflight_vote(self):
        entered, release = self.delay_first_edit()
        closed = asyncio.Event()
        close = self.repo.close_expired_polls
        def track():
            rows = close()
            closed.set()
            return rows
        self.repo.close_expired_polls = track
        vote = asyncio.create_task(self.cog.on_interaction(self.interaction(30, 0)))
        await asyncio.wait_for(entered.wait(), 5)
        self.expire()
        closing = asyncio.create_task(self.close())
        await asyncio.wait_for(closed.wait(), 5)
        release.set()
        await asyncio.gather(vote, closing)
        self.assertTrue(all(button.disabled for button in self.message.view.children))
        self.assertIn('1. A — **1**票', self.message.embed.fields[0].value)

    async def test_temporary_close_failure_is_retried_after_restart(self):
        self.expire()
        error = discord.HTTPException(NS(status=503, reason='temporary'), 'synthetic')
        self.channel.fetch_message.side_effect = [error, self.message]
        await self.close()
        self.cog.engagement_repository = EngagementRepository(self.url)
        self.cog._poll_locks = {}
        await self.close()
        self.assertEqual(self.channel.fetch_message.await_count, 2)
        self.assertTrue(all(button.disabled for button in self.message.view.children))

    async def test_failed_vote_edit_is_corrected_by_final_result(self):
        error = discord.HTTPException(NS(status=503, reason='temporary'), 'synthetic')
        async def fail(**kwargs): raise error
        self.message.edit = fail
        try:
            await self.cog.on_interaction(self.interaction(30, 0))
        except discord.HTTPException:
            pass
        self.message.edit = self.apply_edit
        self.expire()
        await self.close()
        self.assertTrue(all(button.disabled for button in self.message.view.children))
        self.assertIn('1. A — **1**票', self.message.embed.fields[0].value)

    async def test_thread_poll_is_closed_on_discord(self):
        self.channel = MagicMock(spec=discord.Thread)
        self.channel.fetch_message = AsyncMock(return_value=self.message)
        self.guild.get_channel = lambda _: None
        self.expire()
        await self.close()
        self.channel.fetch_message.assert_awaited_once_with(100)
        self.assertTrue(all(button.disabled for button in self.message.view.children))

    async def test_stale_external_writer_ack_requeues_already_synced_latest_revision(self):
        other = EngagementRepository(self.url)
        self.repo.cast_poll_vote(100, 30, 0)
        stale = self.repo.poll_display(100)
        other.cast_poll_vote(100, 31, 1)
        self.expire()
        other.close_expired_polls()
        latest = other.poll_display(100)
        other.mark_poll_display_synced(100, latest['display_revision'])
        self.assertEqual(other.pending_poll_displays(), [])
        # A separate process's older HTTP request finishes after the newer ack.
        await self.apply_edit(embed=self.cog._embed('Question', stale['options'], stale['counts']),
                              view=self.cog._view(100, stale['options']))
        self.repo.mark_poll_display_synced(100, stale['display_revision'])
        self.assertEqual(other.pending_poll_displays(), [100])
        self.cog.engagement_repository = EngagementRepository(self.url)
        await self.close()
        self.assertEqual(other.pending_poll_displays(), [])
        self.assertIn('2. B — **1**票', self.message.embed.fields[0].value)
        self.assertTrue(all(button.disabled for button in self.message.view.children))

    async def test_missing_message_is_terminal_without_recreation(self):
        self.expire()
        self.channel.fetch_message.side_effect = discord.NotFound(NS(status=404, reason='missing'), 'synthetic')
        await self.close()
        await self.close()
        self.assertEqual(self.channel.fetch_message.await_count, 1)
        self.assertEqual(self.repo.pending_poll_displays(), [])
        self.assertEqual(self.repo.poll(100)['status'], 'closed')


class PollUpgradeTests(unittest.TestCase):
    def test_existing_closed_poll_and_vote_survive_upgrade_and_are_pending_once(self):
        with temporary_database(migrate=False) as url, tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in MIGRATIONS.glob('*.sql'):
                if int(path.name[:4]) < 7:
                    (root / path.name).write_bytes(path.read_bytes())
            apply(url, root)
            with transaction(url) as c:
                c.execute("INSERT INTO polls(message_id,guild_id,channel_id,creator_id,question,options_json,closes_at,status,created_at) VALUES(100,1,10,20,'Question','[\"A\",\"B\"]',1,'closed',1)")
                c.execute('INSERT INTO poll_votes VALUES(100,30,1,1)')
            self.assertIn('0007_poll_display_sync.sql', apply(url)['applied'])
            self.assertEqual(apply(url)['applied'], [])
            repo = EngagementRepository(url)
            poll = repo.poll_display(100)
            self.assertEqual(poll['status'], 'closed')
            self.assertEqual(poll['counts'], [0, 1])
            self.assertEqual((poll['guild_id'], poll['channel_id'], poll['creator_id']), (1, 10, 20))
            self.assertEqual(repo.pending_poll_displays(), [100])
            repo.mark_poll_display_synced(100, poll['display_revision'])
            self.assertEqual(repo.pending_poll_displays(), [])


class MinigameControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_hands_and_disabled_feature(self):
        from cogs.engagement.minigames import MinigamesCog
        game = object.__new__(MinigamesCog)
        enabled = [True]
        game.guild_settings = NS(module_enabled=lambda *args: enabled[0])
        response = AsyncMock()
        interaction = NS(guild=NS(id=1), response=response)
        wins = {('rock', 'scissors'), ('paper', 'rock'), ('scissors', 'paper')}
        for player in ('rock', 'paper', 'scissors'):
            for opponent in ('rock', 'paper', 'scissors'):
                with patch('cogs.engagement.minigames.random.choice', return_value=opponent):
                    await MinigamesCog.rps.callback(game, interaction, NS(value=player))
                expected = '引き分け' if player == opponent else 'あなたの勝ち' if (player, opponent) in wins else 'Botの勝ち'
                self.assertIn(expected, response.send_message.await_args.args[0])
        enabled[0] = False
        await MinigamesCog.rps.callback(game, interaction, NS(value='rock'))
        self.assertTrue(response.send_message.await_args.kwargs['ephemeral'])
