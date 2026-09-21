"""Feature-owned storage, registration and worker lifecycle contracts."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from api_support import ApiFixture
from features.contracts import Binding
from features.defaults import RepositorySettingsAccess
from guild_settings import GuildSettingsRepository
from social.providers.registry import ADAPTERS, build_adapters
import social_worker


class DedicatedSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.api = ApiFixture(Path(temporary.name), self.addCleanup)
        self.addCleanup(self.api.client.close)

    def test_dedicated_storage_override_roundtrip_revision_and_generic_write_denial(self):
        modules = GuildSettingsRepository(self.api.database)
        for feature, url in [('tickets', 'tickets/settings'), ('reaction_roles', 'reaction-roles/settings')]:
            with self.subTest(feature=feature):
                modules.set_module(1, feature, enabled=True, settings={'wrong_store': True}, expected_revision=0)
                generic = f'/api/v1/guilds/1/modules/{feature}'
                before = self.api.client.get(generic).json()
                self.assertNotIn('wrong_store', before['settings'])
                self.assertEqual(before['revision'], 0)
                body = {**before['settings'], 'enabled': False, 'revision': 0}
                saved = self.api.client.put(f'/api/v1/guilds/1/{url}', json=body, headers=self.api.headers)
                self.assertEqual(saved.status_code, 200, saved.text)
                self.assertEqual(saved.json()['revision'], 1)
                reloaded = self.api.client.get(generic).json()
                self.assertEqual(reloaded['revision'], saved.json()['revision'])
                for key in before['settings']:
                    if key not in {'guild_id', 'updated_at'}:
                        self.assertEqual(reloaded['settings'][key], saved.json()[key], key)
                stale = self.api.client.put(f'/api/v1/guilds/1/{url}', json=body, headers=self.api.headers)
                self.assertEqual(stale.status_code, 409)
                denied = self.api.client.put(generic, json={'enabled': True, 'settings': {}, 'revision': 1}, headers=self.api.headers)
                self.assertEqual(denied.status_code, 404)
                self.assertEqual(modules.get_module(1, feature)['settings'], {'wrong_store': True})

    def test_dedicated_access_copies_reads_and_forwards_revision(self):
        raw = {'enabled': True, 'revision': 7, 'items': [1]}
        calls = []
        store = SimpleNamespace(settings=lambda guild: raw,
            save_settings=lambda guild, value, revision: calls.append((guild, value, revision)) or raw)
        access = RepositorySettingsAccess(store)
        access.read(1)['settings']['items'].append(2)
        self.assertEqual(raw['items'], [1])
        access.save(1, enabled=False, settings=raw, expected_revision=7)
        self.assertEqual(calls, [(1, {**raw, 'enabled': False}, 7)])

    def test_leveling_additional_permissions_and_validation_do_not_bypass_common_checks(self):
        from dashboard.discord_api import PERMISSION_BITS
        self.api.discord.guild_resources.return_value = ([{'id': '10', 'type': 0}], [{'id': '500', 'name': 'reward'}], PERMISSION_BITS['send_messages'])
        url = '/api/v1/guilds/1/modules/leveling'
        for values in ({'voice_enabled': True}, {'text_role_rewards': [{'level': 1, 'role_id': '500'}]}):
            response = self.api.client.put(url, headers=self.api.headers, json={'enabled': True, 'revision': 0,
                'settings': {'text_notification_channel_id': '10', **values}})
            self.assertEqual(response.status_code, 422)
        self.assertEqual(GuildSettingsRepository(self.api.database).get_module(1, 'leveling')['revision'], 0)


class WorkerRegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_registered_workers_run_once(self):
        first, second = AsyncMock(), AsyncMock()
        with patch.object(social_worker, 'resolve_bindings', return_value=(first, second)) as resolve:
            await social_worker.main()
        first.assert_awaited_once_with()
        second.assert_awaited_once_with()
        self.assertEqual([b.id for b in resolve.call_args.args[0]], ['social_worker'])

    async def test_invalid_worker_binding_starts_nothing(self):
        registry = SimpleNamespace(for_process=lambda process: (Binding('missing', 'worker', 'missing_g3_worker:main'),))
        with patch.object(social_worker, 'REGISTRY', registry), self.assertRaisesRegex(ValueError, 'Cannot resolve binding'):
            await social_worker.main()

    async def test_worker_failure_cancels_sibling_and_runs_cleanup(self):
        started, stopped = asyncio.Event(), asyncio.Event()
        async def sibling():
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                stopped.set()
        async def failure():
            await started.wait()
            raise RuntimeError('worker_failed')
        with patch.object(social_worker, 'resolve_bindings', return_value=(sibling, failure)):
            with self.assertRaises(ExceptionGroup):
                await social_worker.main()
        self.assertTrue(stopped.is_set())


class ProviderRegistrationTests(unittest.TestCase):
    def test_each_provider_has_one_owned_implementation(self):
        settings, client = object(), object()
        adapters = build_adapters(settings, client)
        self.assertEqual(set(adapters), {'youtube', 'twitch', 'tiktok', 'x', 'instagram'})
        self.assertEqual(len(ADAPTERS), len(adapters))
        for name, adapter in adapters.items():
            self.assertEqual(type(adapter).__module__, f'social.providers.{name}')
            self.assertIs(adapter.settings, settings)
            self.assertIs(adapter.client, client)
