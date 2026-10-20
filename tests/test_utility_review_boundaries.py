import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
from cogs.engagement.echo import _build_embed
from cogs.engagement.gemini import AICog


class EchoInputBoundaries(unittest.TestCase):
    def test_invalid_colors_and_hostless_urls_are_rejected_before_discord(self):
        values = dict.fromkeys(('title', 'description', 'color', 'url', 'author_name', 'author_url', 'author_icon_url', 'footer_text', 'footer_icon_url', 'thumbnail_url', 'image_url', 'fields_json'))
        values.update(title='Synthetic', timestamp=False)
        for field, invalid in (('color', '-1'), ('color', '1000000'), ('url', 'https://')):
            with self.subTest(field=field, invalid=invalid), self.assertRaises(ValueError):
                _build_embed(**{**values, field: invalid})
        for color in ('#000000', '#FFFFFF'):
            self.assertLessEqual(_build_embed(**{**values, 'color': color}).colour.value, 0xffffff)


class GeneratedResponseBoundaries(unittest.IsolatedAsyncioTestCase):
    async def test_long_generated_text_remains_available_and_does_not_ping(self):
        for text in ('x' * 2000, '界' * 2001, '@everyone synthetic'):
            with self.subTest(length=len(text)):
                cog = AICog.__new__(AICog)
                cog.bot = SimpleNamespace(settings=SimpleNamespace(gemini_model='synthetic-model'))
                cog.client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=AsyncMock(return_value=SimpleNamespace(text=text)))))
                async def send(content=None, **kwargs):
                    if content and len(content) > 2000:
                        raise ValueError('Synthetic Discord content length rejection')
                interaction = SimpleNamespace(response=SimpleNamespace(defer=AsyncMock()), followup=SimpleNamespace(send=AsyncMock(side_effect=send)))
                await AICog.gemini.callback(cog, interaction, 'synthetic prompt')
                args, kwargs = interaction.followup.send.call_args
                if 'file' in kwargs:
                    self.assertEqual(kwargs['file'].fp.read().decode('utf-8'), text)
                else:
                    self.assertEqual(args[0], text)
                self.assertEqual(kwargs['allowed_mentions'].to_dict(), discord.AllowedMentions.none().to_dict())

