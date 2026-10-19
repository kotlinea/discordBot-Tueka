"""Welcome destination validation through authenticated module API."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from api_support import ApiFixture
from dashboard.discord_api import ADMINISTRATOR, PERMISSION_BITS
from features.defaults import ModuleSettingsAccess
from features.registry import FEATURES


class MembershipBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.api = ApiFixture(Path(temporary.name), self.addCleanup)
        self.addCleanup(self.api.client.close)
        self.url = '/api/v1/guilds/1/modules/welcome'
        self.send = PERMISSION_BITS['view_channel'] | PERMISSION_BITS['send_messages']
        self.embed = self.send | PERMISSION_BITS['embed_links']
        self.resources(self.embed)

    def resources(self, channel_permissions, guild_permissions=None):
        self.api.discord.guild_resources.return_value = ([
            {'id': '10', 'type': 0, 'name': 'welcome', 'bot_permissions': str(channel_permissions)},
            {'id': '11', 'type': 2, 'name': 'voice', 'bot_permissions': str(self.embed)},
            {'id': '100', 'type': 4, 'name': 'category', 'bot_permissions': str(self.embed)},
        ], [{'id': '500', 'name': 'member'}], self.embed if guild_permissions is None else guild_permissions)

    def payload(self, event='welcome', **overrides):
        settings = {f'{event}_enabled': True, f'{event}_channel_id': '10',
            f'{event}_format': 'text', f'{event}_content': 'Hello {user}'}
        settings.update(overrides)
        return {'enabled': True, 'revision': 0, 'settings': settings}

    def save(self, payload):
        return self.api.client.put(self.url, json=payload, headers=self.api.headers)

    def test_rejects_voice_and_category_for_each_enabled_event(self):
        for event in ('welcome', 'leave'):
            for channel in ('11', '100'):
                with self.subTest(event=event, channel=channel):
                    value = self.payload(event, **{f'{event}_channel_id': channel})
                    self.assertEqual(self.save(value).status_code, 422)

    def test_rejects_each_missing_effective_channel_permission(self):
        for event in ('welcome', 'leave'):
            for missing in ('view_channel', 'send_messages'):
                with self.subTest(event=event, missing=missing):
                    self.resources(self.embed & ~PERMISSION_BITS[missing])
                    self.assertEqual(self.save(self.payload(event)).status_code, 422)

    def test_embed_requires_effective_embed_links_for_both_events(self):
        self.resources(self.send)
        for event in ('welcome', 'leave'):
            with self.subTest(event=event):
                self.assertEqual(self.save(self.payload(event, **{f'{event}_format': 'embed'})).status_code, 422)

    def test_text_does_not_require_embed_links_and_round_trips(self):
        self.resources(self.send)
        result = self.save(self.payload())
        self.assertEqual(result.status_code, 200, result.text)
        read = self.api.client.get(self.url)
        self.assertEqual(read.json()['settings'], result.json()['settings'])

    def test_embed_accepts_effective_channel_permission_overwrite(self):
        # Guild-wide Embed Links may be absent when allowed by the destination overwrite.
        self.resources(self.embed, self.send)
        result = self.save(self.payload(welcome_format='embed'))
        self.assertEqual(result.status_code, 200, result.text)

    def test_administrator_can_send_without_individual_channel_bits(self):
        self.resources(ADMINISTRATOR, ADMINISTRATOR)
        result = self.save(self.payload(welcome_format='embed'))
        self.assertEqual(result.status_code, 200, result.text)

    def test_disabled_event_ignores_destination_type_and_permission(self):
        self.resources(0)
        result = self.save(self.payload(welcome_enabled=False, welcome_channel_id='11'))
        self.assertEqual(result.status_code, 200, result.text)

    def test_disabled_module_keeps_existing_type_validation_contract(self):
        self.resources(0)
        value = self.payload(welcome_channel_id='11')
        value['enabled'] = False
        result = self.save(value)
        self.assertEqual(result.status_code, 200, result.text)

    def test_off_with_deleted_resource_still_rejected_by_shared_membership_check(self):
        value = self.payload(welcome_channel_id='999')
        value['enabled'] = False
        self.assertEqual(self.save(value).status_code, 422)

    def test_valid_welcome_does_not_hide_invalid_leave(self):
        value = self.payload(leave_enabled=True, leave_channel_id='11', leave_content='Bye')
        self.assertEqual(self.save(value).status_code, 422)

    def test_autorole_cross_guild_role_still_rejected(self):
        response = self.api.client.put('/api/v1/guilds/1/modules/autorole', headers=self.api.headers,
            json={'enabled': True, 'revision': 0, 'settings': {'default_role_id': '999'}})
        self.assertEqual(response.status_code, 422)

    def test_rejection_preserves_saved_settings_and_revision(self):
        saved = self.save(self.payload()).json()
        self.resources(0)
        value = {**saved, 'settings': {**saved['settings'], 'welcome_content': 'Changed'}}
        self.assertEqual(self.save(value).status_code, 422)
        read = self.api.client.get(self.url).json()
        self.assertEqual(read['revision'], saved['revision'])
        self.assertEqual(read['settings'], saved['settings'])

    def test_existing_four_method_factory_can_register_and_save_without_resource_hook(self):
        def legacy_factory(feature):
            def create(context):
                access = ModuleSettingsAccess(context.guild_settings_repository, feature.id)
                return SimpleNamespace(read=access.read, validate=access.validate,
                    save=access.save, additional_permissions=access.additional_permissions)
            return create

        factories = tuple(legacy_factory(feature) for feature in FEATURES if feature.settings_factory)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        with patch('dashboard.api.settings.resolve_bindings', return_value=factories):
            legacy_api = ApiFixture(Path(temporary.name), self.addCleanup)
        self.addCleanup(legacy_api.client.close)
        saved = legacy_api.client.put(self.url, headers=legacy_api.headers,
            json={'enabled': False, 'revision': 0, 'settings': {'welcome_content': 'Legacy factory'}})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()['settings']['welcome_content'], 'Legacy factory')
        self.assertEqual(legacy_api.client.get(self.url).json()['revision'], saved.json()['revision'])
