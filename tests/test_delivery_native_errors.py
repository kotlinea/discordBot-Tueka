import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord

from discord_io import DiscordFailure
from reaction_roles.discord_adapter import DiscordReactionRoleAdapter
from social.discord_adapter import DiscordSocialAdapter


class DeliveryNativeErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_history_forbidden_keeps_publication_uncertain_in_both_adapters(self):
        channel = MagicMock(spec=discord.TextChannel)
        channel.send = AsyncMock()

        async def history(**kwargs):
            raise discord.Forbidden(SimpleNamespace(status=403, reason='Forbidden'), 'No history access')
            yield

        channel.history = history
        guild = SimpleNamespace(get_channel=lambda _: channel, get_channel_or_thread=lambda _: channel)
        bot = SimpleNamespace(user=SimpleNamespace(id=99), get_guild=lambda _: guild)
        config = {'id': 1, 'created_at': 100, 'guild_id': 1, 'channel_id': 10, 'source': 'bot',
                  'embed': {'title': '', 'description': '', 'color': '#5865F2'}}
        for name in ('reaction_roles', 'social'):
            with self.subTest(adapter=name):
                with self.assertRaises(DiscordFailure) as failure:
                    if name == 'reaction_roles':
                        await DiscordReactionRoleAdapter(bot).publish(config, recover=True)
                    else:
                        await DiscordSocialAdapter(bot).send(1, 10, '', {}, None, 'receipt', recover=True, created_at=100)
                self.assertTrue(failure.exception.partial)
                channel.send.assert_not_awaited()

    async def test_role_recovery_rejects_newer_human_audit_entry(self):
        entry = SimpleNamespace(target=SimpleNamespace(id=20), user=SimpleNamespace(id=30), reason='manual',
                                before=SimpleNamespace(roles=[]), after=SimpleNamespace(roles=[SimpleNamespace(id=40)]))

        async def audit_logs(**kwargs):
            yield entry

        guild = SimpleNamespace(audit_logs=audit_logs)
        adapter = DiscordReactionRoleAdapter(SimpleNamespace(user=SimpleNamespace(id=99), get_guild=lambda _: guild))
        operation = {'id': 1, 'guild_id': 1, 'user_id': 20, 'created_at': 100}
        self.assertFalse(await adapter.owns_role_change(operation, 40))
        entry.user.id, entry.reason = 99, 'Tueka role operation:1'
        self.assertTrue(await adapter.owns_role_change(operation, 40))
