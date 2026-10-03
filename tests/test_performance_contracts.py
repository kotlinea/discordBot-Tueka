"""Behavior and work-count contracts for the bounded performance changes."""
import asyncio
from contextlib import contextmanager
from dataclasses import replace
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import discord
from community import CommunityRepository
from cogs.community.leveling import LevelingCog
from cogs.community.live_stats import LiveStatsCog
from dashboard.api.context import create_context
from dashboard.api.features import FeaturePresenter
from db_support import prepare_database
from features.defaults import ModuleSettingsAccess
from features.registry import FEATURES
from guild_settings import GuildSettingsRepository
from social.worker import SocialWorker


@contextmanager
def trace_connections(repository):
    connections = []
    original = repository._connection

    @contextmanager
    def traced():
        with original() as connection:
            spy = Mock(wraps=connection)
            connections.append(spy)
            yield spy

    with patch.object(repository, '_connection', traced):
        yield connections


class PerformanceRepositoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.url = prepare_database(Path(temp.name) / 'performance.db', self.addCleanup)
        self.settings = GuildSettingsRepository(self.url)

    def test_xp_update_uses_one_transaction_and_returns_its_own_result(self):
        repository = CommunityRepository(self.url)
        for add, get in ((repository.add_xp, 'get_user'), (repository.add_voice_xp, 'get_voice_user')):
            with trace_connections(repository) as connections, \
                 patch.object(repository, get, side_effect=AssertionError('Extra read')):
                self.assertEqual(add(1, 10, 5), {'xp': 5})
                self.assertEqual(add(1, 10, 7), {'xp': 12})
                self.assertEqual(len(connections), 2)
                self.assertEqual([connection.execute.call_count for connection in connections], [1, 1])

    def test_batch_settings_match_single_reads_and_use_one_transaction(self):
        self.settings.set_module(1, 'welcome', enabled=True, settings={'welcome_channel_id': 10})
        self.settings.set_module(1, 'leveling', enabled=False)
        self.settings.set_module(2, 'welcome', enabled=False)
        ids = ['welcome', 'leveling', 'live_stats']
        expected = {key: self.settings.get_module(1, key) for key in ids}
        with trace_connections(self.settings) as connections:
            self.assertEqual(self.settings.get_modules(1, [*ids, 'welcome']), expected)
            self.assertEqual(len(connections), 1)
            connections[0].execute.assert_called_once()
        with patch.object(self.settings, '_connection', side_effect=AssertionError('Empty batch')):
            self.assertEqual(self.settings.get_modules(1, []), {})
        expected['welcome']['settings']['welcome_channel_id'] = 999
        self.assertEqual(self.settings.get_module(1, 'welcome')['settings']['welcome_channel_id'], 10)
        with patch('guild_settings.repository.normalize', side_effect=AssertionError('Flag needs no JSON')):
            self.assertTrue(self.settings.module_enabled(1, 'welcome'))
            self.assertFalse(self.settings.module_enabled(2, 'welcome'))
            self.assertFalse(self.settings.module_enabled(3, 'welcome'))

    def test_presenter_batch_preserves_factories_subclasses_and_independent_store(self):
        context = create_context(self.url, None)
        presenter = FeaturePresenter(context)
        before = [presenter.feature_payload(1, feature, 0) for feature in FEATURES]
        with patch.object(context.guild_settings_repository, 'get_modules', wraps=context.guild_settings_repository.get_modules) as batch:
            self.assertEqual(presenter.feature_payloads(1, FEATURES, 0), before)
            batch.assert_called_once()

        class CustomAccess(ModuleSettingsAccess):
            def read(self, guild_id):
                return {'enabled': True, 'revision': 7, 'settings': {'custom': True}}

        normal = next(feature for feature in FEATURES if not feature.settings_factory)
        custom = CustomAccess(context.guild_settings_repository, normal.id)
        context.feature_settings[normal.id] = custom
        with patch.object(CustomAccess, 'read', wraps=custom.read) as read:
            self.assertEqual(presenter.feature_payloads(1, [normal], 0)[0]['revision'], 7)
            read.assert_called_once_with(1)
        independent = Mock(get_module=Mock(return_value={'enabled': False, 'revision': 8, 'settings': {}}))
        context.feature_settings[normal.id] = ModuleSettingsAccess(independent, normal.id)
        self.assertEqual(presenter.feature_payloads(1, [normal], 0)[0]['revision'], 8)
        independent.get_module.assert_called_once_with(1, normal.id)
        context.feature_settings[normal.id] = ModuleSettingsAccess(context.guild_settings_repository, normal.id)
        factory_feature = replace(normal, settings_factory='custom:factory')
        with patch.object(context.guild_settings_repository, 'get_module', wraps=context.guild_settings_repository.get_module) as read:
            presenter.feature_payloads(1, [factory_feature], 0)
            read.assert_called_once_with(1, normal.id)


class LevelingPerformanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = LevelingCog.__new__(LevelingCog)
        self.cog.repository = Mock()
        self.cog.guild_settings = Mock()
        self.cog.last_xp_time = {}
        self.cog._on_level_up = AsyncMock()
        self.member = MagicMock(spec=discord.Member)
        self.member.id, self.member.bot = 10, False
        self.guild = SimpleNamespace(id=1)
        self.member.guild = self.guild
        self.message = SimpleNamespace(author=self.member, guild=self.guild)
        self.cog.guild_settings.get_module.return_value = {'enabled': True, 'settings': {'text_role_rewards': []}}

    async def test_cooldown_boundary_and_level_notification_share_one_settings_read(self):
        self.cog.repository.add_xp.return_value = {'xp': 100}
        with patch('cogs.community.leveling.time.monotonic', return_value=0), patch('cogs.community.leveling.random.randint', return_value=20):
            await self.cog.on_message(self.message)
        self.cog.repository.get_user.assert_not_called()
        self.cog._on_level_up.assert_awaited_once_with(self.member, 1, {'text_role_rewards': []}, 'text')
        self.cog.guild_settings.get_module.assert_called_once()
        self.cog.guild_settings.reset_mock()
        with patch('cogs.community.leveling.time.monotonic', return_value=59.9):
            await self.cog.on_message(self.message)
        self.cog.guild_settings.get_module.assert_not_called()
        with patch('cogs.community.leveling.time.monotonic', return_value=60):
            await self.cog.on_message(self.message)
        self.cog.guild_settings.get_module.assert_called_once()

    async def test_disabled_and_failed_awards_do_not_start_cooldown(self):
        self.cog.guild_settings.get_module.return_value['enabled'] = False
        await self.cog.on_message(self.message)
        self.cog.repository.add_xp.assert_not_called()
        self.cog.guild_settings.get_module.return_value['enabled'] = True
        self.cog.repository.add_xp.side_effect = RuntimeError('DB failure')
        with self.assertRaisesRegex(RuntimeError, 'DB failure'):
            await self.cog.on_message(self.message)
        self.assertEqual(self.cog.last_xp_time, {})

    async def test_voice_award_and_expired_cooldown_cleanup(self):
        self.member.voice = SimpleNamespace(self_mute=False, mute=False, self_deaf=False, deaf=False)
        self.guild.afk_channel = None
        self.guild.voice_channels = [SimpleNamespace(members=[self.member])]
        self.cog.bot = Mock(get_guild=Mock(return_value=self.guild))
        self.cog.guild_settings.enabled_module_guild_ids.return_value = [1]
        settings = {'voice_enabled': True, 'voice_allow_solo': True, 'voice_xp_per_minute': 5}
        self.cog.guild_settings.get_module.return_value = {'enabled': True, 'settings': settings}
        self.cog.repository.add_voice_xp.return_value = {'xp': 100}
        self.cog.last_xp_time = {(1, 1): 0, (1, 2): 60}
        with patch('cogs.community.leveling.time.monotonic', return_value=60):
            await LevelingCog.voice_xp_tick.coro(self.cog)
        self.assertEqual(self.cog.last_xp_time, {(1, 2): 60})
        self.cog.repository.get_voice_user.assert_not_called()
        self.cog._on_level_up.assert_awaited_once_with(self.member, 1, settings, 'voice')

    async def test_level_up_retains_role_reward_and_notification(self):
        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        role = MagicMock(spec=discord.Role)
        role.managed, role.is_default.return_value, role.__ge__.return_value = False, False, False
        self.guild.me = SimpleNamespace(top_role=Mock())
        self.guild.get_role = Mock(return_value=role)
        self.guild.get_channel = Mock(return_value=channel)
        self.member.roles = []
        self.member.add_roles = AsyncMock()
        await LevelingCog._on_level_up(self.cog, self.member, 1,
            {'text_role_rewards': [{'level': 1, 'role_id': 20}], 'text_notification_channel_id': 30}, 'text')
        self.member.add_roles.assert_awaited_once_with(role, reason='Level reward at level 1')
        channel.send.assert_awaited_once()


class LiveStatsPerformanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = LiveStatsCog.__new__(LiveStatsCog)
        self.cog._pending, self.cog._locks = set(), {}
        self.channel = MagicMock(spec=discord.VoiceChannel)
        self.channel.name = 'old'
        self.channel.edit = AsyncMock()
        self.guild = SimpleNamespace(id=1, members=[SimpleNamespace(bot=False)], member_count=1,
            roles=[1], get_channel=Mock(return_value=self.channel))
        self.cog.bot = Mock(get_guild=Mock(side_effect=lambda key: self.guild if key == 1 else None))
        self.cog.guild_settings = Mock()
        self.cog.guild_settings.get_module.return_value = {'enabled': True,
            'settings': {'stats_channel_id': 10, 'stats_template': '{members}:{bots}:{humans}:{roles}'}}

    async def test_event_burst_is_one_update_and_continuous_events_are_not_deferred(self):
        member = SimpleNamespace(guild=self.guild)
        for _ in range(100):
            await self.cog.on_member_join(member)
            await self.cog.on_member_remove(member)
        self.cog.guild_settings.get_module.assert_not_called()
        await LiveStatsCog.flush_live_stats.coro(self.cog)
        self.cog.guild_settings.get_module.assert_called_once_with(1, 'live_stats')
        self.channel.edit.assert_awaited_once_with(name='1:0:1:1', reason='Live statistics update')
        await self.cog.on_guild_role_create(member)
        await self.cog.on_guild_role_delete(member)
        await LiveStatsCog.flush_live_stats.coro(self.cog)
        self.assertEqual(self.channel.edit.await_count, 2)
        self.assertNotIn('on_voice_state_update', dict(LiveStatsCog.__cog_listeners__))
        self.assertNotIn('on_member_update', dict(LiveStatsCog.__cog_listeners__))

    async def test_disabled_missing_unchanged_and_departed_guild_skip_discord(self):
        self.cog.guild_settings.get_module.return_value['enabled'] = False
        await self.cog.update_stats(self.guild)
        self.cog.guild_settings.get_module.return_value['enabled'] = True
        self.guild.get_channel.return_value = None
        await self.cog.update_stats(self.guild)
        self.guild.get_channel.return_value = self.channel
        self.channel.name = '1:0:1:1'
        await self.cog.update_stats(self.guild)
        self.channel.edit.assert_not_awaited()
        self.cog._pending.add(1)
        self.cog.bot.get_guild.side_effect = None
        self.cog.bot.get_guild.return_value = None
        await self.cog.on_guild_remove(self.guild)
        self.assertEqual(self.cog._pending, set())
        self.assertEqual(self.cog._locks, {})

    async def test_failures_retry_next_cycle_and_periodic_refresh_shares_lock(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def edit(**kwargs):
            entered.set()
            await release.wait()
        self.channel.edit.side_effect = edit
        self.cog._pending.add(1)
        self.cog.guild_settings.enabled_module_guild_ids.return_value = [1]
        first = asyncio.create_task(LiveStatsCog.flush_live_stats.coro(self.cog))
        await entered.wait()
        second = asyncio.create_task(LiveStatsCog.refresh_live_stats.coro(self.cog))
        await asyncio.sleep(0)
        self.assertEqual(self.channel.edit.await_count, 1)
        release.set()
        await asyncio.gather(first, second)
        self.channel.edit.side_effect = discord.HTTPException(SimpleNamespace(status=500, reason='error'), 'test')
        with self.assertLogs('cogs.community.live_stats', level='WARNING'):
            await self.cog.update_stats(self.guild)
        self.assertEqual(self.cog._pending, {1})
        self.channel.edit.side_effect = None
        await LiveStatsCog.flush_live_stats.coro(self.cog)
        self.assertEqual(self.cog._pending, set())
        self.cog.guild_settings.enabled_module_guild_ids.side_effect = RuntimeError('DB unavailable')
        with self.assertLogs('cogs.community.live_stats', level='WARNING'):
            await LiveStatsCog.refresh_live_stats.coro(self.cog)
        self.cog.guild_settings.enabled_module_guild_ids.side_effect = None
        await LiveStatsCog.refresh_live_stats.coro(self.cog)

    async def test_unload_cancels_both_tasks_and_clears_state(self):
        ready = asyncio.Event()
        bot = Mock(settings=SimpleNamespace(database_url='unused'), wait_until_ready=AsyncMock(side_effect=ready.wait))
        with patch('cogs.community.live_stats.GuildSettingsRepository'):
            cog = LiveStatsCog(bot)
        tasks = [cog.refresh_live_stats.get_task(), cog.flush_live_stats.get_task()]
        await asyncio.sleep(0)
        cog._pending.add(1)
        cog._locks[1] = asyncio.Lock()
        cog.cog_unload()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.assertTrue(all(task.cancelled() for task in tasks))
        self.assertEqual((cog._pending, cog._locks), (set(), {}))


class SocialPurgePerformanceTests(unittest.TestCase):
    def test_clock_boundary_long_pause_failure_completion_and_restart(self):
        now = [0]
        with patch('social.worker.SocialRepository') as factory:
            worker = SocialWorker(SimpleNamespace(database_url='unused'), clock=lambda: now[0])
            repository = factory.return_value
            now[0] = 3599
            worker._purge_history_if_due()
            repository.purge_social_history.assert_not_called()
            def purge(**kwargs):
                now[0] += 10
            repository.purge_social_history.side_effect = purge
            now[0] = 3600
            worker._purge_history_if_due()
            repository.purge_social_history.assert_called_once_with(retention_days=30)
            self.assertEqual(worker._next_purge_at, 7210)
            worker._purge_history_if_due()
            self.assertEqual(repository.purge_social_history.call_count, 1)
            now[0] = 20000
            worker._purge_history_if_due()
            self.assertEqual(repository.purge_social_history.call_count, 2)
            worker._purge_history_if_due()
            self.assertEqual(repository.purge_social_history.call_count, 2)
            now[0] = worker._next_purge_at
            repository.purge_social_history.side_effect = RuntimeError('DB unavailable')
            with self.assertLogs('tueka.social_worker', level='WARNING'):
                worker._purge_history_if_due()
            self.assertEqual(worker._next_purge_at, now[0] + 3600)
            restarted = SocialWorker(SimpleNamespace(database_url='unused'), clock=lambda: now[0])
            self.assertEqual(restarted._next_purge_at, now[0] + 3600)
