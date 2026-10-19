"""Moderation detection scope, Unicode, URL and raid-state regressions."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from moderation.engine import AutoModEngine, MessageContext
from moderation.models import default_rule, validate_rule
from cogs.moderation.runtime import AutoModCog


def rule(trigger, identifier, priority=10, **updates):
    raw = default_rule(trigger)
    raw.update(name=trigger, priority=priority, **updates)
    return {**validate_rule(raw), 'id': identifier}


def cog_for(rules, states):
    cog = AutoModCog.__new__(AutoModCog)
    cog._locks = {}
    cog.engine = AutoModEngine()
    cog.guild_settings = SimpleNamespace(get_module=lambda guild_id, family: states.get(family, {'enabled': True, 'settings': {}}))
    cog._rules = lambda *args: rules
    cog.service = SimpleNamespace(execute_actions=AsyncMock(return_value=[]), log_event=AsyncMock())
    cog.moderation_repository = SimpleNamespace(create_moderation_event=MagicMock(return_value=1), finish_moderation_event=MagicMock(), set_raid_state=MagicMock())
    return cog


class ModerationDetectionBoundaries(unittest.IsolatedAsyncioTestCase):
    async def process(self, cog, content='bad', *, now=1, signal=False):
        context = MessageContext(1, 2, 3, content, now=now)
        if signal:
            await cog._process_signal(context, SimpleNamespace(id=1), None, object(), dedupe_target=str(now))
        else:
            cog._context = lambda *args, **kwargs: context
            message = SimpleNamespace(id=int(now), guild=SimpleNamespace(id=1, name='Guild'), author=SimpleNamespace(id=2),
                                      channel=SimpleNamespace(id=3, name='Channel'), content=content, attachments=[])
            await cog._process(message)

    async def test_disabled_family_cannot_stop_an_enabled_family(self):
        first = rule('keyword', 1, stop_on_match=True, trigger_config={'keywords': ['bad']})
        second = rule('message_rate', 2, priority=20, trigger_config={'limit': 1, 'window_seconds': 10})
        cog = cog_for([first, second], {'automod': {'enabled': False, 'settings': {}}})
        await cog._process_signal(MessageContext(1, 2, 3, 'bad', now=1), SimpleNamespace(id=1), None, object(), dedupe_target='m1')
        self.assertEqual(cog.moderation_repository.create_moderation_event.call_count, 1,
                         'Enabled anti_spam rule must still create its event')

    async def test_family_exemption_cannot_stop_an_unexempt_family(self):
        first = rule('keyword', 1, stop_on_match=True, trigger_config={'keywords': ['bad']})
        second = rule('message_rate', 2, priority=20, trigger_config={'limit': 1, 'window_seconds': 10})
        cog = cog_for([first, second], {'automod': {'enabled': True, 'settings': {'immune_user_ids': [2]}}})
        await cog._process_signal(MessageContext(1, 2, 3, 'bad', now=1), SimpleNamespace(id=1), None, object(), dedupe_target='m1')
        self.assertEqual(cog.moderation_repository.create_moderation_event.call_count, 1)

    async def test_disabled_family_does_not_build_rate_state(self):
        spam = rule('message_rate', 1, trigger_config={'limit': 2, 'window_seconds': 10})
        states = {'anti_spam': {'enabled': False, 'settings': {}}}
        cog = cog_for([spam], states)
        await cog._process_signal(MessageContext(1, 2, 3, 'one', now=1), SimpleNamespace(id=1), None, object(), dedupe_target='m1')
        states['anti_spam']['enabled'] = True
        await cog._process_signal(MessageContext(1, 2, 3, 'two', now=2), SimpleNamespace(id=1), None, object(), dedupe_target='m2')
        cog.moderation_repository.create_moderation_event.assert_not_called()

    async def test_family_scope_filters_both_message_and_signal_paths_before_evaluation(self):
        first = rule('keyword', 1, stop_on_match=True, trigger_config={'keywords': ['bad']})
        second = rule('message_rate', 2, priority=20, trigger_config={'limit': 1, 'window_seconds': 10})
        for signal in (False, True):
            for excluded in ({'enabled': False, 'settings': {}},
                             {'enabled': True, 'settings': {'immune_user_ids': [2]}}):
                with self.subTest(signal=signal, excluded=excluded):
                    cog = cog_for([first, second], {'automod': excluded})
                    await self.process(cog, signal=signal)
                    cog.moderation_repository.create_moderation_event.assert_called_once()
                    self.assertEqual(cog.moderation_repository.create_moderation_event.call_args.kwargs['family'], 'anti_spam')

    async def test_family_exempt_activity_does_not_enter_rate_window(self):
        spam = rule('message_rate', 1, trigger_config={'limit': 2, 'window_seconds': 10})
        for signal in (False, True):
            with self.subTest(signal=signal):
                states = {'anti_spam': {'enabled': True, 'settings': {'immune_user_ids': [2]}}}
                cog = cog_for([spam], states)
                await self.process(cog, now=1, signal=signal)
                self.assertEqual(cog.engine.state_size, 0)
                states['anti_spam']['settings'] = {}
                await self.process(cog, now=2, signal=signal)
                cog.moderation_repository.create_moderation_event.assert_not_called()

    async def test_active_families_preserve_cross_family_priority_and_stop(self):
        first = rule('keyword', 1, stop_on_match=True, trigger_config={'keywords': ['bad']})
        second = rule('message_rate', 2, priority=20, trigger_config={'limit': 1, 'window_seconds': 10})
        for signal in (False, True):
            with self.subTest(signal=signal):
                cog = cog_for([second, first], {})
                await self.process(cog, signal=signal)
                cog.moderation_repository.create_moderation_event.assert_called_once()
                self.assertEqual(cog.moderation_repository.create_moderation_event.call_args.kwargs['family'], 'automod')
                self.assertEqual(cog.engine.state_size, 0)

    async def test_keyword_normalizes_full_width_latin(self):
        banned = rule('keyword', 1, trigger_config={'keywords': ['bad'], 'match': 'contains'})
        self.assertTrue(await AutoModEngine().evaluate(MessageContext(1, 2, 3, '\uff42\uff41\uff44'), [banned]))

    async def test_keyword_normalizes_canonical_combining_forms(self):
        banned = rule('keyword', 1, trigger_config={'keywords': ['\u30ac'], 'match': 'contains'})
        self.assertTrue(await AutoModEngine().evaluate(MessageContext(1, 2, 3, '\u30ab\u3099'), [banned]))

    async def test_keyword_normalization_preserves_casefold_allow_list_and_wildcard(self):
        cases = [('Straße', 'STRASSE', 'contains', [], True),
                 ('ｂａｄ', 'BAD', 'contains', [], True),
                 ('sp*m', 'ＳＰＡＭ', 'wildcard', [], True),
                 ('bad', 'ＢＡＤminton', 'wildcard', [], False),
                 ('bad', 'ＢＡＤ', 'contains', ['ｂａｄ'], False)]
        for keyword, content, mode, allowed, expected in cases:
            with self.subTest(keyword=keyword, content=content, mode=mode):
                banned = rule('keyword', 1, trigger_config={'keywords': [keyword], 'match': mode, 'allow_list': allowed})
                self.assertEqual(bool(await AutoModEngine().evaluate(MessageContext(1, 2, 3, content), [banned])), expected)

    async def test_malformed_media_url_does_not_abort_other_rules(self):
        media = rule('media_only', 1)
        honey = rule('honeypot', 2, priority=20, trigger_config={'channel_ids': [3]})
        matches = await AutoModEngine().evaluate(MessageContext(1, 2, 3, 'https://[.png'), [media, honey])
        self.assertIn(2, [match.rule['id'] for match in matches])

    async def test_malformed_media_url_does_not_hide_valid_media_in_same_message(self):
        media = rule('media_only', 1)
        self.assertFalse(await AutoModEngine().evaluate(MessageContext(1, 2, 3, 'https://[.png https://example.com/file.png'), [media]))

    async def test_new_member_activity_records_raid_state(self):
        recent = rule('new_member_activity', 1)
        cog = cog_for([recent], {})
        cog._context = lambda *args, **kwargs: MessageContext(1, 2, 3, 'hello', joined_at=datetime.now(timezone.utc))
        message = SimpleNamespace(id=4, guild=SimpleNamespace(id=1, name='Guild'), author=SimpleNamespace(id=2),
                                  channel=SimpleNamespace(id=3, name='Channel'), content='hello', attachments=[])
        await cog._process(message)
        cog.moderation_repository.create_moderation_event.assert_called_once()
        cog.moderation_repository.set_raid_state.assert_called_once_with(1, True, source_rule_id=1, lockdown_id=None)

    async def test_control_guild_isolation_and_window_boundary(self):
        spam = rule('message_rate', 1, trigger_config={'limit': 2, 'window_seconds': 10})
        engine = AutoModEngine()
        self.assertFalse(await engine.evaluate(MessageContext(1, 2, 3, now=1), [spam]))
        self.assertFalse(await engine.evaluate(MessageContext(2, 2, 3, now=2), [spam]))
        self.assertTrue(await engine.evaluate(MessageContext(1, 2, 3, now=11), [spam]))


if __name__ == '__main__':
    unittest.main()
