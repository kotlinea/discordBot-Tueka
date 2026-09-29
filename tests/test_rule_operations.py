"""U4 HTTP, transaction and runtime contracts against an isolated PostgreSQL schema."""
import asyncio
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from api_support import ApiFixture
from cogs.moderation.runtime import AutoModCog
from guild_settings import GuildSettingsRepository
from moderation import AutoModEngine, MessageContext, ModerationRepository, default_rule
from moderation.rules import FAMILY_TRIGGERS


class RuleOperationsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.api = ApiFixture(Path(temp.name), self.addCleanup)
        self.addCleanup(self.api.client.close)
        self.repo = ModerationRepository(self.api.database)
        self.settings = GuildSettingsRepository(self.api.database)

    def root(self, family='automod', guild=1):
        return f'/api/v1/guilds/{guild}/moderation/{family}/rules'

    def create(self, family='automod', guild=1, channel=10):
        trigger = {'automod': 'keyword', 'anti_spam': 'message_rate', 'anti_raid': 'join_rate'}[family]
        value = {**default_rule(trigger), 'enabled': False, 'conditions': {'channel_ids': [channel]}}
        if trigger == 'keyword':
            value['trigger_config'] = {'keywords': ['blocked']}
        result = self.api.client.post(self.root(family, guild), json=value, headers=self.api.headers)
        self.assertEqual(result.status_code, 201, result.text)
        return result.json()

    def state(self, items, enabled, family='automod', **kwargs):
        return self.api.client.put(self.root(family) + '/state', json={
            'enabled': enabled, 'items': [{k: item[k] for k in ('id', 'revision')} for item in items]},
            headers=kwargs.pop('headers', self.api.headers), **kwargs)

    def snapshot(self):
        with self.repo._connection() as connection:
            return [connection.execute(f'SELECT * FROM {table} ORDER BY 1,2').fetchall()
                    for table in ('moderation_rules', 'guild_modules', 'moderation_events')]

    def test_templates_are_unsaved_disabled_family_defaults_without_identity(self):
        before = self.snapshot()
        for family, triggers in FAMILY_TRIGGERS.items():
            for trigger in triggers:
                result = self.api.client.get(f'/api/v1/guilds/1/moderation/{family}/templates/{trigger}')
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(result.json(), {**default_rule(trigger), 'enabled': False})
                self.assertFalse({'id', 'revision', 'guild_id', 'created_at'} & result.json().keys())
        for family, trigger in [('automod', 'join_rate'), ('invalid', 'keyword'), ('automod', 'unknown')]:
            self.assertEqual(self.api.client.get(f'/api/v1/guilds/1/moderation/{family}/templates/{trigger}').status_code, 404)
        self.assertEqual(self.snapshot(), before)

    def test_three_families_multiple_same_trigger_toggle_preserves_content_order_history(self):
        for family in FAMILY_TRIGGERS:
            originals = [self.create(family, channel=10), self.create(family, channel=11)]
            self.assertNotEqual(originals[0]['id'], originals[1]['id'])
            self.repo.create_moderation_event(1, family=family, event_type=originals[0]['event_type'],
                source='automod', reason='existing', rule_id=originals[0]['id'])
            history = self.snapshot()[2]
            items = originals
            for enabled in (True, False, True):
                revision = self.settings.get_module(1, 'moderation')['settings']['rules_revision']
                result = self.state(items, enabled, family)
                self.assertEqual(result.status_code, 200, result.text)
                items = result.json()['items']
                self.assertEqual([item['id'] for item in items], [item['id'] for item in originals])
                for original, item in zip(originals, items):
                    self.assertEqual(item['enabled'], enabled)
                    self.assertEqual({k: v for k, v in item.items() if k not in ('enabled', 'revision', 'updated_at')},
                                     {k: v for k, v in original.items() if k not in ('enabled', 'revision', 'updated_at')})
                core = self.settings.get_module(1, 'moderation')
                self.assertEqual(core['settings']['rules_revision'], revision + 1)
                self.assertFalse(core['enabled'])
                self.assertEqual(self.snapshot()[2], history)
                self.assertEqual(len(self.repo.moderation_rules(1, family=family)), 2)
            before = self.snapshot()
            self.assertEqual(self.state(items, True, family).status_code, 200)
            self.assertEqual(self.snapshot(), before)  # same-state retry does not touch revisions

    def test_invalid_selections_conflicts_and_csrf_change_nothing(self):
        first, second = self.create(), self.create()
        foreign, other = self.create(guild=2), self.create('anti_spam')
        for selected, status in [([first, {**second, 'revision': 999}], 409),
                                 ([first, foreign], 422), ([first, other], 422),
                                 ([first, {**second, 'id': 999999}], 422), ([first, first], 422), ([], 422)]:
            before = self.snapshot()
            self.assertEqual(self.state(selected, True).status_code, status)
            self.assertEqual(self.snapshot(), before)
        before = self.snapshot()
        self.assertEqual(self.state([first, second], True, headers={}).status_code, 403)
        self.api.discord.can_manage.return_value = False
        self.assertEqual(self.state([first, second], True).status_code, 403)
        self.assertEqual(self.snapshot(), before)

    def test_required_strict_input_and_activation_validation(self):
        first, second = self.create(), self.create()
        for body in [{'items': [first]}, {'enabled': 'true', 'items': [first]},
                     {'enabled': True, 'items': [{'id': first['id']}]},
                     {'enabled': True, 'items': [{'id': True, 'revision': 1}]},
                     {'enabled': True, 'items': [first] * 201}]:
            before = self.snapshot()
            self.assertEqual(self.api.client.put(self.root() + '/state', json=body, headers=self.api.headers).status_code, 422)
            self.assertEqual(self.snapshot(), before)
        with self.repo._connection() as connection:
            connection.execute('UPDATE moderation_rules SET trigger_config_json=%s WHERE id=%s', (json.dumps({'keywords': []}), second['id']))
        before = self.snapshot()
        self.assertEqual(self.state([first, second], True).status_code, 422)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.state([first, second], False).status_code, 200)  # invalid rules can still be stopped

    def test_overlapping_bulk_requests_have_one_winner_and_one_conflict(self):
        items = [self.create(), self.create()]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.state(items, True), range(2)))
        self.assertEqual(sorted(result.status_code for result in results), [200, 409])
        self.assertEqual([item['revision'] for item in self.repo.moderation_rules(1)], [2, 2])

    def test_failure_after_row_update_rolls_back_states_and_runtime_generation(self):
        items = [self.create(), self.create()]
        before = self.snapshot()
        with patch('moderation.repository.moderation_settings', side_effect=ValueError('injected after rule UPDATE')):
            self.assertEqual(self.state(items, True).status_code, 422)
        self.assertEqual(self.snapshot(), before)

    def test_partial_selection_mixed_states_preserves_other_rules_and_stop_order(self):
        first, second, untouched = self.create(), self.create(), self.create()
        ordered = self.repo.reorder_moderation_rules(1, 'automod', [
            {'id': item['id'], 'revision': item['revision'], 'stop_on_match': index == 0}
            for index, item in enumerate((second, untouched, first))])
        selected = [item for item in ordered if item['id'] != untouched['id']]
        selected[0] = self.state([selected[0]], True).json()['items'][0]
        before = self.repo.moderation_rules(1)
        generation = self.settings.get_module(1, 'moderation')['settings']['rules_revision']
        result = self.state(selected, True)
        self.assertEqual(result.status_code, 200, result.text)
        after = self.repo.moderation_rules(1)
        self.assertEqual([row['id'] for row in after], [row['id'] for row in before])
        for old, new in zip(before, after):
            if old['id'] in (untouched['id'], second['id']):
                self.assertEqual(new, old)
            else:
                self.assertEqual(new['revision'], old['revision'] + 1)
                self.assertEqual(new['priority'], old['priority'])
                self.assertEqual(new['stop_on_match'], old['stop_on_match'])
        self.assertEqual(self.settings.get_module(1, 'moderation')['settings']['rules_revision'], generation + 1)

    def test_bulk_and_single_edit_serialize_on_the_same_lock(self):
        items = [self.create(), self.create()]
        def write(bulk):
            return self.state(items, True) if bulk else self.api.client.put(
                self.root() + f"/{items[0]['id']}", json={**items[0], 'name': 'Edited'}, headers=self.api.headers)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, (True, False)))
        self.assertEqual(sorted(result.status_code for result in results), [200, 409])
        rows = self.repo.moderation_rules(1)
        if results[0].status_code == 200:
            self.assertTrue(all(row['enabled'] for row in rows))
            self.assertEqual(rows[0]['name'], items[0]['name'])
        else:
            self.assertFalse(any(row['enabled'] for row in rows))
            self.assertEqual(rows[0]['name'], 'Edited')
            self.assertEqual(rows[1]['revision'], items[1]['revision'])

    def test_new_draft_post_keeps_source_and_history_unchanged(self):
        original = self.create()
        before = self.repo.moderation_rule(1, original['id'])
        draft = {key: value for key, value in original.items()
                 if key not in {'id', 'revision', 'guild_id', 'created_at', 'updated_at'}}
        draft.update(name='A different purpose', enabled=False, conditions={'channel_ids': ['11']})
        result = self.api.client.post(self.root(), json=draft, headers=self.api.headers)
        self.assertEqual(result.status_code, 201, result.text)
        self.assertNotEqual(result.json()['id'], original['id'])
        self.assertEqual(result.json()['revision'], 1)
        self.assertFalse(result.json()['enabled'])
        self.assertEqual(self.repo.moderation_rule(1, original['id']), before)

    def test_runtime_cache_refresh_and_restarted_engine_use_preserved_rules(self):
        items = [self.create(channel=10), self.create(channel=11)]
        runtime = SimpleNamespace(moderation_repository=self.repo, _cache={})
        def rules():
            return AutoModCog._rules(runtime, 1, self.settings.get_module(1, 'moderation'))
        self.assertEqual(rules(), [])
        items = self.state(items, True).json()['items']
        self.assertEqual(len(rules()), 2)
        for channel, expected in zip((10, 11), items):
            matches = asyncio.run(AutoModEngine().evaluate(MessageContext(1, 20, channel, content='blocked'), rules()))
            self.assertEqual([match.rule['id'] for match in matches], [expected['id']])
        items = self.state(items, False).json()['items']
        self.assertEqual(rules(), [])
        self.state(items, True)
        runtime = SimpleNamespace(moderation_repository=ModerationRepository(self.api.database), _cache={})
        self.assertEqual([item['id'] for item in rules()], [item['id'] for item in items])
        matches = asyncio.run(AutoModEngine().evaluate(MessageContext(1, 20, 11, content='blocked'), rules()))
        self.assertEqual([match.rule['id'] for match in matches], [items[1]['id']])
