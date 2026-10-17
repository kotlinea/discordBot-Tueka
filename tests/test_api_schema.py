"""HTTP schema, persistence, and generated-client contracts."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from api_support import ApiFixture
from scripts.generate_api import artifacts


class ApiSchemaTests(unittest.TestCase):
    def test_feature_maturity_is_independent_of_environment_enablement(self):
        from guild_settings import GuildSettingsRepository
        repository=GuildSettingsRepository(self.api.database)
        for enabled in (False,True):
            repository.set_module(1,'suggestions',enabled=enabled)
            response=self.api.client.get('/api/v1/guilds/1/features')
            self.assertEqual(response.status_code,200,response.text)
            items=response.json()['items']
            self.assertEqual(len(items),25)
            self.assertTrue(all(item['maturity']=='improving' for item in items))
            self.assertEqual(next(item for item in items if item['id']=='suggestions')['enabled'],enabled)

    def test_manual_action_feature_state_tracks_the_executor_module_without_exposing_settings(self):
        from guild_settings import GuildSettingsRepository
        repository = GuildSettingsRepository(self.api.database)
        for enabled in (True, False):
            repository.set_module(1, 'moderation', enabled=enabled, settings={'default_log_channel_id':10})
            repository.set_module(1, 'moderation_actions', enabled=not enabled)
            response = self.api.client.get('/api/v1/guilds/1/features')
            self.assertEqual(response.status_code,200,response.text)
            feature = next(item for item in response.json()['items'] if item['id']=='moderation_actions')
            self.assertEqual(feature['enabled'],enabled)
            self.assertEqual(feature['settings'],{})

    def test_purge_rejects_forum_but_lock_accepts_it_before_queueing(self):
        from guild_settings import GuildSettingsRepository
        from moderation import ModerationRepository
        GuildSettingsRepository(self.api.database).set_module(1, 'moderation', enabled=True)
        channels, roles, permissions = self.api.discord.guild_resources.return_value
        self.api.discord.guild_resources.return_value = ([*channels, {'id':'15','type':15}], roles, permissions)
        root = '/api/v1/guilds/1/moderation/actions'
        repository = ModerationRepository(self.api.database)
        body = {'action':'purge','channel_id':'15','reason':'channel support test','confirmed':True}
        rejected = self.api.client.post(root,json=body,headers=self.api.headers)
        self.assertEqual(rejected.status_code,422,rejected.text)
        with repository._connection() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) AS count FROM moderation_action_requests').fetchone()['count'],0)
        accepted = self.api.client.post(root,json={**body,'action':'lock'},headers=self.api.headers)
        self.assertEqual(accepted.status_code,202,accepted.text)

    def test_manual_action_duration_limits_reject_before_queueing_and_preserve_boundaries(self):
        from guild_settings import GuildSettingsRepository
        from moderation import ModerationRepository
        GuildSettingsRepository(self.api.database).set_module(1, 'moderation', enabled=True)
        root = '/api/v1/guilds/1/moderation/actions'
        repository = ModerationRepository(self.api.database)
        for action, maximum in (('timeout', 40320), ('lockdown', 1440)):
            body = {'action': action, 'target_user_id': '30', 'reason': 'boundary test',
                    'confirmed': True, 'confirmation': '1', 'duration_minutes': maximum + 1}
            with repository._connection() as connection:
                before = connection.execute('SELECT COUNT(*) AS count FROM moderation_action_requests').fetchone()['count']
            rejected = self.api.client.post(root, json=body, headers=self.api.headers)
            self.assertEqual(rejected.status_code, 422, rejected.text)
            with repository._connection() as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) AS count FROM moderation_action_requests').fetchone()['count'], before)
            accepted = self.api.client.post(root, json={**body, 'duration_minutes': maximum}, headers=self.api.headers)
            self.assertEqual(accepted.status_code, 202, accepted.text)
            with repository._connection() as connection:
                import json
                row = connection.execute('SELECT options_json FROM moderation_action_requests WHERE id=%s', (accepted.json()['request_id'],)).fetchone()
                self.assertEqual(json.loads(row['options_json'])['duration_minutes'], maximum)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.api = ApiFixture(Path(self.temp.name), self.addCleanup)
        self.addCleanup(self.api.client.close)

    def test_generated_artifacts_match_the_real_router(self):
        for path, expected in artifacts().items():
            self.assertTrue(path.exists(), str(path))
            self.assertEqual(hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest(),
                             hashlib.sha256(expected.encode()).hexdigest(), str(path))

    def test_request_and_response_references_are_resolved_and_successes_are_typed(self):
        document = self.api.app.openapi()

        def visit(value):
            if isinstance(value, dict):
                if '$ref' in value:
                    target = document
                    for key in value['$ref'][2:].split('/'):
                        target = target[key]
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(document)
        for path, methods in document['paths'].items():
            for method, operation in methods.items():
                for status, response in operation['responses'].items():
                    if status.startswith('2') and status != '204' and '/attachments/' not in path:
                        schema = response['content']['application/json']['schema']
                        self.assertIn('$ref', schema, (path, method))

    def test_form_constraint_is_shared_with_openapi_and_rejects_without_mutation(self):
        root = '/api/v1/guilds/1/suggestions/settings'
        before = self.api.client.get(root).json()
        body = {**before, 'settings': {**before['settings'], 'form_fields': [
            {'key': 'idea', 'label': 'x' * 46, 'style': 'short', 'required': False,
             'placeholder': '', 'min_length': 0, 'max_length': 100}]}}
        response = self.api.client.put(root, json=body, headers=self.api.headers)
        self.assertEqual(response.status_code, 422, response.text)
        detail = response.json()['detail']
        self.assertEqual(detail['code'], 'validation_failed')
        self.assertEqual(detail['errors'][0]['path'], 'settings.form_fields.0.label')
        self.assertEqual(self.api.client.get(root).json(), before)
        request = self.api.app.openapi()['paths']['/api/v1/guilds/{guild_id}/suggestions/settings']['put']['requestBody']['content']['application/json']['schema']
        self.assertEqual(request['properties']['settings']['properties']['form_fields']['items']['properties']['label']['maxLength'], 45)
        body['settings']['form_fields'][0]['label'] = 'x' * 45
        saved = self.api.client.put(root, json=body, headers=self.api.headers)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(self.api.client.get(root).json(), saved.json())
        stale = self.api.client.put(root, json=body, headers=self.api.headers)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(set(stale.json()['detail']), {'code', 'message', 'errors'})

    def test_ticket_configuration_roundtrip_and_internal_ids_are_numeric(self):
        root = '/api/v1/guilds/1/tickets'

        def create(path, body):
            response = self.api.client.post(root + path, json=body, headers=self.api.headers)
            self.assertEqual(response.status_code, 201, response.text)
            return response.json()

        form = create('/forms', {'name': 'Contact', 'title': 'Contact', 'fields': [
            {'key': 'question', 'label': 'Question', 'style': 'paragraph', 'required': True,
             'min_length': 1, 'max_length': 100, 'placeholder': ''}]})
        team = create('/teams', {'name': 'Support', 'role_ids': ['500'], 'user_ids': [],
                                'admin_user_ids': [], 'notification_channel_id': '10', 'enabled': True})
        panel = create('/panels', {'name': 'Support', 'mode': 'channel', 'category_id': '100',
                                  'team_id': team['id'], 'form_id': form['id']})
        self.assertIsInstance(panel['id'], int)
        self.assertEqual(panel['team_id'], team['id'])
        self.assertEqual(panel['form_id'], form['id'])
        self.assertEqual(panel['category_id'], '100')
        listing = self.api.client.get(root + '/panels').json()
        self.assertEqual(listing['items'], [panel])
        self.assertIsNone(listing['next'])
        bundle = self.api.client.get(root + '/panels/' + str(panel['id']) + '/editor')
        self.assertEqual(bundle.status_code, 200, bundle.text)
        preview = self.api.client.post(root + '/panels/preview', json=bundle.json())
        self.assertEqual(preview.status_code, 200, preview.text)
        stats = self.api.client.get(root + '/stats')
        self.assertEqual(stats.status_code, 200, stats.text)
        self.assertEqual(stats.json()['panels'][0]['id'], panel['id'])

    def test_ticket_bundle_create_read_update_preserves_shared_message_identity(self):
        root = '/api/v1/guilds/1/tickets'
        team_response = self.api.client.post(root + '/teams', headers=self.api.headers, json={
            'name': 'Recovery test', 'role_ids': [], 'user_ids': [], 'admin_user_ids': [],
            'notification_channel_id': None, 'enabled': True})
        self.assertEqual(team_response.status_code, 201, team_response.text)
        team = team_response.json()
        response = self.api.client.post(root + '/panels/bundles', headers=self.api.headers, json={
            'panel': {'name': 'First', 'mode': 'channel', 'category_id': '100', 'team_id': team['id']},
            'deployment': {'name': 'Entry', 'channel_id': '10', 'title': 'Recovery test'}})
        self.assertEqual(response.status_code, 201, response.text)
        first = response.json()
        message_id = first['deployments'][0]['id']
        self.assertEqual(first['deployment']['panel_message_id'], message_id)
        self.assertEqual(first['deployment']['position'], 0)
        editor = root + '/panels/' + str(first['panel']['id']) + '/editor'
        loaded = self.api.client.get(editor)
        self.assertEqual(loaded.status_code, 200, loaded.text)
        self.assertEqual(loaded.json(), first)
        first['deployment']['title'] = 'Updated entry'
        updated = self.api.client.put(root + '/panels/' + str(first['panel']['id']) + '/bundle',
                                      headers=self.api.headers, json=first)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()['deployment']['panel_message_id'], message_id)
        self.assertEqual(len(updated.json()['deployments']), 1)
        self.assertEqual(self.api.client.get(editor).json()['deployment']['title'], 'Updated entry')
        second = self.api.client.post(root + '/panels/bundles', headers=self.api.headers, json={
            'panel': {'name': 'Second', 'mode': 'channel', 'category_id': '100', 'team_id': team['id']},
            'deployment': {**updated.json()['deployment'], 'position': 0}})
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(second.json()['deployment']['panel_message_id'], message_id)
        self.assertEqual(second.json()['deployment']['position'], 0)
        reread = self.api.client.get(editor)
        self.assertEqual(reread.status_code, 200, reread.text)
        self.assertEqual(reread.json()['deployment']['position'], 1)
        self.assertEqual(reread.json()['deployment']['panel_message_id'], message_id)

    def test_framework_domain_and_json_validation_share_one_error_shape(self):
        cases = [self.api.client.get('/api/v1/guilds/invalid/modules/welcome'),
                 self.api.client.get('/api/v1/guilds/1/reaction-roles/messages/999'),
                 self.api.client.put('/api/v1/preferences', content='{', headers=self.api.headers)]
        for response in cases:
            with self.subTest(status=response.status_code):
                self.assertIn(response.status_code, (404, 422))
                self.assertEqual(set(response.json()['detail']), {'code', 'message', 'errors'})

    def test_disable_preserves_settings_and_large_discord_id(self):
        discord_id = '1234567890123456789'
        channels, roles, permissions = self.api.discord.guild_resources.return_value
        self.api.discord.guild_resources.return_value = ([*channels, {'id': discord_id, 'type': 0}], roles, permissions)
        root = '/api/v1/guilds/1/suggestions/settings'
        draft = self.api.client.get(root).json()
        draft.update(enabled=True)
        draft['settings']['channel_id'] = discord_id
        enabled = self.api.client.put(root, json=draft, headers=self.api.headers)
        self.assertEqual(enabled.status_code, 200, enabled.text)
        draft = enabled.json()
        draft['enabled'] = False
        disabled = self.api.client.put(root, json=draft, headers=self.api.headers)
        self.assertEqual(disabled.status_code, 200, disabled.text)
        reloaded = self.api.client.get(root).json()
        self.assertFalse(reloaded['enabled'])
        self.assertEqual(reloaded['settings']['channel_id'], discord_id)

    def test_moderation_history_and_lockdown_preserve_snowflakes(self):
        from moderation.repository import ModerationRepository
        repository = ModerationRepository(self.api.database)
        user_id, moderator_id = 1234567890123456789, 1234567890123456790
        case_id = repository.add_case(1, user_id, 'warn', 'reason', moderator_id)
        response = self.api.client.get(f'/api/v1/guilds/1/moderation/infractions/{user_id}')
        self.assertEqual(response.status_code, 200, response.text)
        case = response.json()['cases'][0]
        self.assertEqual(case['id'], case_id)
        self.assertEqual(case['guild_id'], '1')
        self.assertEqual(case['user_id'], str(user_id))
        self.assertEqual(case['moderator_id'], str(moderator_id))
        self.assertIsInstance(case['created_at'], int)
        repository.start_lockdown(1, reason='test', started_by=moderator_id, unlock_at=None)
        overview = self.api.client.get('/api/v1/guilds/1/overview')
        self.assertEqual(overview.status_code, 200, overview.text)
        self.assertEqual(overview.json()['moderation']['lockdown']['started_by'], str(moderator_id))
        attachment = self.api.app.openapi()['paths']['/api/v1/tickets/attachments/{attachment_id}']['get']
        self.assertEqual(set(attachment['responses']['200']['content']), {'application/octet-stream'})

    def test_events_without_optional_subjects_remain_readable(self):
        from moderation.repository import ModerationRepository
        from reaction_roles.repository import ReactionRoleRepository
        actor_id = 1234567890123456789
        moderation = ModerationRepository(self.api.database)
        event_id = moderation.create_moderation_event(1, family='automod', event_type='message_create',
            source='test', reason='Monitor only', actor_id=actor_id, target_id=actor_id, mode='monitor')
        events = self.api.client.get('/api/v1/guilds/1/moderation/events')
        self.assertEqual(events.status_code, 200, events.text)
        event = events.json()['items'][0]
        self.assertEqual(event['id'], event_id)
        self.assertIsNone(event['case_id'])
        self.assertIsNone(event['channel_id'])
        self.assertEqual(event['guild_id'], '1')
        self.assertEqual(event['actor_id'], str(actor_id))
        self.assertEqual(event['target_id'], str(actor_id))
        overview = self.api.client.get('/api/v1/guilds/1/overview')
        self.assertEqual(overview.status_code, 200, overview.text)
        self.assertEqual(overview.json()['moderation']['events'][0], event)
        ReactionRoleRepository(self.api.database).audit(1, None, 'settings_updated', 'success', actor_id=actor_id)
        roles = self.api.client.get('/api/v1/guilds/1/reaction-roles/events')
        self.assertEqual(roles.status_code, 200, roles.text)
        role_event = roles.json()['items'][0]
        self.assertEqual(role_event['guild_id'], '1')
        self.assertEqual(role_event['actor_id'], str(actor_id))
        for field in ('message_config_id', 'emoji_key', 'reason', 'user_id', 'role_id'):
            self.assertIsNone(role_event[field], field)
