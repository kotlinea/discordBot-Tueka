import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from cogs.moderation.trust_score import TrustCog


class TrustPresentationBoundaries(unittest.IsolatedAsyncioTestCase):
    async def test_maximum_valid_reasons_fit_one_discord_field(self):
        for count, reason in ((0, ''), (1, '界' * 1000), (10, '界' * 1000), (10, '🙂' * 1000)):
            with self.subTest(count=count, unicode=reason[:1]):
                cog = TrustCog.__new__(TrustCog)
                cog.guild_settings = Mock()
                cog.guild_settings.module_enabled.return_value = True
                cog.guild_settings.get_module.return_value = {'settings': {}}
                cog.moderation_repository = Mock()
                cog.moderation_repository.trust_score.return_value = {
                    'score': 0, 'events': [{'category': 'warn', 'weight': -10, 'reason': reason}] * count,
                }
                interaction = SimpleNamespace(guild=SimpleNamespace(id=1), response=SimpleNamespace(send_message=AsyncMock()))
                member = SimpleNamespace(id=2, display_name='Synthetic member')
                await TrustCog.trust_score.callback(cog, interaction, member)
                payload = interaction.response.send_message.call_args.kwargs
                self.assertTrue(payload['ephemeral'])
                embed = payload['embed']
                self.assertLessEqual(len(embed), 6000)
                self.assertLessEqual(len(embed.fields[0].value), 1024)
                self.assertNotEqual(embed.fields[0].value, '')
                self.assertEqual(cog.moderation_repository.trust_score.call_args.args, (1, 2, 90))

