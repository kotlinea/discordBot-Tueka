"""Leveling failure isolation, reward recovery and disable boundaries."""
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import discord
from cogs.community.leveling import LevelingCog
from community import CommunityRepository
from database.testing import temporary_database
from guild_settings import GuildSettingsRepository


class LevelingReviewBoundaries(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        context = temporary_database()
        self.url = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.repository = CommunityRepository(self.url)
        self.settings = GuildSettingsRepository(self.url)
        self.settings.set_module(1, 'leveling', enabled=True, settings={
            'text_notification_channel_id': 30, 'voice_notification_channel_id': 30,
            'text_role_rewards': [{'level': 1, 'role_id': 20}],
            'voice_enabled': True, 'voice_allow_solo': True, 'voice_xp_per_minute': 5})
        self.role = MagicMock(spec=discord.Role)
        self.role.managed = False
        self.role.is_default.return_value = False
        self.role.__ge__.return_value = False
        self.channel = MagicMock(spec=discord.TextChannel)
        self.channel.send = AsyncMock()
        self.guild = SimpleNamespace(id=1, me=SimpleNamespace(top_role=Mock()), afk_channel=None,
            get_role=Mock(return_value=self.role), get_channel=Mock(return_value=self.channel))
        self.member = MagicMock(spec=discord.Member)
        self.member.id, self.member.bot, self.member.guild = 10, False, self.guild
        self.member.mention, self.member.roles = '<@10>', []
        self.member.add_roles = AsyncMock()
        self.member.voice = SimpleNamespace(self_mute=False, mute=False, self_deaf=False, deaf=False)
        self.guild.voice_channels = [SimpleNamespace(id=40, members=[self.member])]
        self.message = SimpleNamespace(id=123, guild=self.guild, author=self.member)
        self.cog = LevelingCog.__new__(LevelingCog)
        self.cog.repository, self.cog.guild_settings, self.cog.last_xp_time = self.repository, self.settings, {}
        self.cog.bot = Mock(get_guild=Mock(return_value=self.guild), wait_until_ready=AsyncMock())

    async def award(self, now):
        with patch('cogs.community.leveling.time.monotonic', return_value=now), \
             patch('cogs.community.leveling.random.randint', return_value=20):
            await self.cog.on_message(self.message)

    def second_member(self):
        member = MagicMock(spec=discord.Member)
        member.id, member.bot, member.guild, member.voice = 11, False, self.guild, self.member.voice
        self.guild.voice_channels[0].members.append(member)
        return member

    async def test_notification_failure_does_not_stop_remaining_voice_awards(self):
        self.second_member()
        self.repository.add_voice_xp(1, 10, 95)
        self.channel.send.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason='denied'), 'test')
        await LevelingCog.voice_xp_tick.coro(self.cog)
        self.assertEqual(self.repository.get_voice_user(1, 10)['xp'], 100)
        self.assertEqual(self.repository.get_voice_user(1, 11)['xp'], 5)
        self.channel.send.side_effect = None
        await LevelingCog.voice_xp_tick.coro(self.cog)
        self.assertEqual(self.repository.get_voice_user(1, 11)['xp'], 10)

    async def test_repaired_role_permission_recovers_without_another_level(self):
        self.repository.add_xp(1, 10, 80)
        self.member.add_roles.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason='denied'), 'test')
        await self.award(0)
        async def acquired(role, **kwargs):
            self.member.roles.append(role)
        self.member.add_roles.side_effect = acquired
        await self.award(60)
        self.assertEqual(self.repository.get_user(1, 10)['xp'], 120)
        self.assertIn(self.role, self.member.roles)
        self.assertEqual(self.member.add_roles.await_count, 2)
        await self.award(120)
        self.assertEqual(self.member.add_roles.await_count, 2)
        self.assertEqual(self.channel.send.await_count, 1)

    async def test_off_after_first_member_discord_wait_blocks_second_member_xp(self):
        self.second_member()
        self.repository.add_voice_xp(1, 10, 95)
        async def disable(*args, **kwargs):
            self.settings.set_module(1, 'leveling', enabled=False)
        self.channel.send.side_effect = disable
        await LevelingCog.voice_xp_tick.coro(self.cog)
        self.assertFalse(self.settings.module_enabled(1, 'leveling'))
        self.assertEqual(self.repository.get_voice_user(1, 11)['xp'], 0)

    async def test_member_db_failure_isolated_from_next_eligible_member(self):
        self.second_member()
        original = self.repository.add_voice_xp
        def fail_first(guild_id, user_id, amount):
            if user_id == 10:
                raise RuntimeError('isolated test database failure')
            return original(guild_id, user_id, amount)
        with patch.object(self.repository, 'add_voice_xp', side_effect=fail_first):
            await LevelingCog.voice_xp_tick.coro(self.cog)
        self.assertEqual(self.repository.get_voice_user(1, 10)['xp'], 0)
        self.assertEqual(self.repository.get_voice_user(1, 11)['xp'], 5)

    async def test_voice_only_off_after_wait_blocks_next_member(self):
        self.second_member()
        self.repository.add_voice_xp(1, 10, 95)
        async def disable_voice(*args, **kwargs):
            settings = self.settings.get_module(1, 'leveling')['settings']
            self.settings.set_module(1, 'leveling', enabled=True, settings={**settings, 'voice_enabled': False})
        self.channel.send.side_effect = disable_voice
        await LevelingCog.voice_xp_tick.coro(self.cog)
        self.assertTrue(self.settings.module_enabled(1, 'leveling'))
        self.assertEqual(self.repository.get_voice_user(1, 11)['xp'], 0)

    async def test_guild_failure_isolated_from_another_guild(self):
        other = self.second_member()
        other_guild = SimpleNamespace(id=2, afk_channel=None, me=self.guild.me,
            voice_channels=[SimpleNamespace(id=41, members=[other])])
        other.guild = other_guild
        self.settings.set_module(2, 'leveling', enabled=True, settings={
            'voice_enabled': True, 'voice_allow_solo': True, 'voice_xp_per_minute': 5})
        def guild(guild_id):
            if guild_id == 1:
                raise RuntimeError('guild lookup test failure')
            return other_guild
        self.cog.bot.get_guild.side_effect = guild
        await LevelingCog.voice_xp_tick.coro(self.cog)
        self.assertEqual(self.repository.get_voice_user(2, 11)['xp'], 5)
        self.assertEqual(self.repository.get_voice_user(1, 11)['xp'], 0)

    async def test_enumeration_failure_does_not_prevent_next_tick(self):
        with patch.object(self.settings, 'enabled_module_guild_ids', side_effect=[RuntimeError('lookup failure'), [1]]):
            await LevelingCog.voice_xp_tick.coro(self.cog)
            self.assertEqual(self.repository.get_voice_user(1, 10)['xp'], 0)
            await LevelingCog.voice_xp_tick.coro(self.cog)
        self.assertEqual(self.repository.get_voice_user(1, 10)['xp'], 5)
