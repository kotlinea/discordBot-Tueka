"""Real Discord adapter receipt matching with mocked transport only."""
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
import discord
from appeals.discord_adapter import DiscordAppealAdapter
from discord_io import DiscordFailure


class DiscordAppealTests(unittest.IsolatedAsyncioTestCase):
    def bot(self,messages):
        channel=SimpleNamespace(send=AsyncMock(return_value=SimpleNamespace(id=123)))
        async def history():
            for message in messages:yield message
        channel.history=lambda **_:history()
        user=SimpleNamespace(create_dm=AsyncMock(return_value=channel))
        bot=SimpleNamespace(fetch_user=AsyncMock(return_value=user),user=SimpleNamespace(id=99))
        return bot,channel

    def item(self):return dict(id=1,guild_id=1,author_id=10,expires_at=int(time.time())+100,body='Generated private text')

    async def test_receipt_recovery_never_sends_a_second_dm(self):
        message=SimpleNamespace(id=777,author=SimpleNamespace(id=99),embeds=[discord.Embed().set_footer(text='Tueka private conversation:5')])
        bot,channel=self.bot([message])
        self.assertEqual(await DiscordAppealAdapter(bot).notify(self.item(),5,recover=True),777)
        channel.send.assert_not_awaited()

    async def test_missing_or_foreign_receipt_requires_reconciliation(self):
        message=SimpleNamespace(id=777,author=SimpleNamespace(id=10),embeds=[discord.Embed().set_footer(text='Tueka private conversation:5')])
        bot,channel=self.bot([message])
        with self.assertRaises(DiscordFailure) as error:await DiscordAppealAdapter(bot).notify(self.item(),5,recover=True)
        self.assertTrue(error.exception.partial);channel.send.assert_not_awaited()

    async def test_fresh_send_disables_mentions_and_checks_expiry(self):
        bot,channel=self.bot([])
        self.assertEqual(await DiscordAppealAdapter(bot).notify(self.item(),5,recover=False),123)
        options=channel.send.call_args.kwargs
        self.assertEqual(options['allowed_mentions'].to_dict()['parse'],[])
        self.assertEqual(options['embed'].description,'Generated private text')
        expired={**self.item(),'expires_at':0}
        with self.assertRaises(DiscordFailure):await DiscordAppealAdapter(bot).notify(expired,6,recover=False)
        self.assertEqual(channel.send.await_count,1)
