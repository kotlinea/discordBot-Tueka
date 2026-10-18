"""Bound the complete public card without losing review state or stored answers."""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from suggestions.discord_adapter import DiscordSuggestionAdapter
from suggestions.models import normalize_settings
from suggestions.presentation import suggestion_embed


def maximum_card():
    settings = normalize_settings({'form_fields': [
        {'key': f'answer{i}', 'label': str(i) * 45, 'style': 'paragraph',
         'required': True, 'min_length': 1, 'max_length': 4000}
        for i in range(5)]})
    item = {'id': 9223372036854775807, 'guild_id': 9223372036854775807,
            'channel_id': 9223372036854775807, 'message_id': 9223372036854775807,
            'author_id': 9223372036854775807, 'status': 'approved',
            'answers': {f'answer{i}': str(i) * 1024 for i in range(5)},
            'review_reason': '審' * 1000, 'reviewer_id': 9223372036854775807,
            'discussion_thread_id': 9223372036854775807,
            'upvotes': 9223372036854775807, 'downvotes': 9223372036854775807,
            'created_at': 1900000000}
    return item, settings


class SuggestionPresentationTests(unittest.TestCase):
    def test_long_review_keeps_complete_metadata_and_all_answer_fields_within_budget(self):
        item, settings = maximum_card()
        original = copy.deepcopy(item)
        for status in ('reviewing', 'approved', 'rejected', 'implemented'):
            with self.subTest(status=status):
                item['status'] = status
                embed = suggestion_embed(item, settings)
                self.assertEqual(len(embed), 6000)
                self.assertEqual([field.name for field in embed.fields[:5]], [str(i) * 45 for i in range(5)])
                self.assertTrue(all(1 <= len(field.value) <= 1024 for field in embed.fields))
                self.assertEqual(next(field.value for field in embed.fields if field.name == '審査理由'), item['review_reason'])
                self.assertIn(str(item['discussion_thread_id']), next(field.value for field in embed.fields if field.name == 'Discussion'))
                self.assertIn(str(item['reviewer_id']), embed.footer.text)
                self.assertTrue(embed.footer.text.endswith(f"Tueka suggestion:{item['id']}:{item['created_at']}"))
                self.assertTrue(any(field.value.endswith('…') for field in embed.fields[:5]))
        item['status'] = original['status']
        self.assertEqual(item, original)

    def test_additional_metadata_uses_the_same_complete_card_budget(self):
        item, settings = maximum_card()
        item.update(category='分' * 40, tags=[str(i) + '標' * 39 for i in range(10)],
                    merged_into=9223372036854775806,
                    merged_target={'channel_id': item['channel_id'], 'message_id': item['message_id']})
        embed = suggestion_embed(item, settings)
        self.assertLessEqual(len(embed), 6000)
        self.assertEqual(next(field.value for field in embed.fields if field.name == '審査理由'), item['review_reason'])
        self.assertEqual(len(embed.fields[:5]), 5)

    def test_card_below_limit_is_unchanged_including_short_and_missing_answers(self):
        item, settings = maximum_card()
        item.update(review_reason=None, discussion_thread_id=None, reviewer_id=None)
        for answers in (item['answers'], {'answer0': '短い回答', 'answer1': ''}, {}):
            with self.subTest(count=len(answers)):
                item['answers'] = answers
                embed = suggestion_embed(item, settings)
                self.assertLessEqual(len(embed), 6000)
                self.assertEqual([field.value for field in embed.fields], [value for value in answers.values() if value])


class SuggestionPresentationAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_review_sync_sends_valid_complete_card_and_closed_controls(self):
        item, settings = maximum_card()
        message = SimpleNamespace(edit=AsyncMock())
        channel = SimpleNamespace(fetch_message=AsyncMock(return_value=message))
        adapter = DiscordSuggestionAdapter(SimpleNamespace())
        adapter.channel = lambda *_: channel
        await adapter.sync(item, settings)
        payload = message.edit.call_args.kwargs
        self.assertLessEqual(len(payload['embed']), 6000)
        self.assertEqual(next(field.value for field in payload['embed'].fields if field.name == '審査理由'), item['review_reason'])
        controls = payload['view'].children
        self.assertTrue(all(button.disabled for button in controls if not button.custom_id.endswith(':implemented')))
