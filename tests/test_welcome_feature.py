"""Welcome registration through HTTP persistence and Discord input boundaries."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
from api_support import ApiFixture
from cogs.community.welcome import WelcomeCog
from cogs.community.autorole import AutoroleCog
from guild_settings import GuildSettingsRepository


class WelcomeFeatureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.api = ApiFixture(Path(temporary.name), self.addCleanup)
        self.addCleanup(self.api.client.close)
        self.url = '/api/v1/guilds/1/modules/welcome'
        self.bot = SimpleNamespace(settings=self.api.settings)
        self.storage = GuildSettingsRepository(self.api.database)

    def save(self, value, **kwargs):
        return self.api.client.put(self.url, json=value, headers=kwargs.get('headers', self.api.headers))

    def payload(self, **settings):
        return {'enabled': True, 'revision': 0, 'settings': {'welcome_enabled': True, 'welcome_channel_id': '10', 'welcome_content': 'Hello {user}', **settings}}

    def member(self):
        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()
        guild = SimpleNamespace(id=1, name='Guild', member_count=2, members=[], get_channel=lambda identifier: channel if identifier == 10 else None, get_role=lambda identifier: 'role')
        return SimpleNamespace(id=20, mention='<@20>', name='Member', display_name='Member', guild=guild, add_roles=AsyncMock()), channel

    def test_registered_settings_save_reload_delivery_and_disable(self):
        saved = self.save(self.payload(leave_enabled=True, leave_channel_id='10', leave_content='Bye {username}', leave_format='embed'))
        self.assertEqual(saved.status_code, 200, saved.text)
        read = self.api.client.get(self.url).json()
        self.assertEqual(read['settings'], saved.json()['settings'])
        member, channel = self.member()
        cog = WelcomeCog(self.bot)
        asyncio.run(cog.on_member_join(member))
        self.assertEqual(channel.send.call_args.args, ('Hello <@20>',))
        mentions = channel.send.call_args.kwargs['allowed_mentions']
        self.assertFalse(mentions.everyone)
        self.assertFalse(mentions.roles)
        self.assertEqual(mentions.users, [member])
        asyncio.run(cog.on_member_remove(member))
        self.assertEqual(channel.send.call_args.kwargs['embed'].description, 'Bye Member')
        disabled = self.save({**saved.json(), 'enabled': False})
        self.assertEqual(disabled.status_code, 200, disabled.text)
        channel.send.reset_mock()
        asyncio.run(cog.on_member_join(member))
        asyncio.run(cog.on_member_remove(member))
        channel.send.assert_not_called()
        self.assertEqual(disabled.json()['settings']['welcome_content'], 'Hello {user}')

    def test_validation_revision_and_authorization_remain_outside_override(self):
        invalid = [self.payload(welcome_channel_id='999'), self.payload(welcome_content=''), self.payload(welcome_content='x' * 2001)]
        for payload in invalid:
            self.assertEqual(self.save(payload).status_code, 422)
        self.assertEqual(self.save(self.payload(), headers={}).status_code, 403)
        self.api.discord.can_manage.return_value = False
        self.assertEqual(self.save(self.payload()).status_code, 403)
        self.api.discord.can_manage.return_value = True
        saved = self.save(self.payload())
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(self.save(self.payload(welcome_content='Overwrite')).status_code, 409)
        self.assertEqual(self.api.client.get(self.url).json()['settings'], saved.json()['settings'])
        self.api.session.pop('session_id')
        self.assertEqual(self.api.client.get(self.url).status_code, 401)
        self.assertEqual(self.save(self.payload()).status_code, 401)

    def test_autorole_is_independent_and_welcome_never_assigns_roles(self):
        self.storage.set_module(1, 'autorole', enabled=True, settings={'default_role_id': 500})
        member, channel = self.member()
        asyncio.run(WelcomeCog(self.bot).on_member_join(member))
        member.add_roles.assert_not_called()
        channel.send.assert_not_called()
        asyncio.run(AutoroleCog(self.bot).on_member_join(member))
        member.add_roles.assert_awaited_once_with('role', reason='Default role on join')
        self.storage.set_module(1, 'autorole', enabled=False)
        member.add_roles.reset_mock()
        asyncio.run(AutoroleCog(self.bot).on_member_join(member))
        member.add_roles.assert_not_called()
