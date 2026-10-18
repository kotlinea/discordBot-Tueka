"""Registration failures must be caught before runtime factories start work."""
import ast
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from features.catalog import Registry
from features.contracts import Binding, Category, Feature
from features.defaults import ModuleSettingsAccess
from features.loading import resolve_bindings, validate_extensions
from features.registry import FEATURES, REGISTRY, BOT_EXTENSIONS

ROOT = Path(__file__).resolve().parents[1]


def feature(name='sample', **kwargs):
    return Feature(name, 'example', dashboard=False, **kwargs)


def catalog(*items, bindings=()):
    return Registry((Category('example', 'nav.example', items, bindings),))


class FeatureRegistrationTests(unittest.TestCase):
    def test_existing_public_metadata_order_and_extension_order_are_preserved(self):
        baseline = json.loads((ROOT / 'dashboard/frontend/src/test/fixtures/feature_metadata.json').read_text())
        # Explicit relocation/split map; the immutable public baseline stays unchanged.
        relocation = {
            'cogs.general': ('cogs.general', 'cogs.engagement.echo', 'cogs.engagement.calculate', 'cogs.engagement.roll'),
            'cogs.ai': ('cogs.engagement.gemini',),
            'cogs.leveling': ('cogs.community.leveling',),
            'cogs.moderation': ('cogs.moderation.moderation',),
            'cogs.safety': ('cogs.moderation.action_support.direct_commands',),
            'cogs.reaction_roles': ('cogs.community.reaction_roles',),
            'cogs.automod': ('cogs.moderation.runtime',),
            'cogs.moderation_commands': ('cogs.moderation.moderation_actions',),
            'cogs.community': ('cogs.community.live_stats', 'cogs.community.temporary_voice'),
            'cogs.tickets': ('cogs.community.tickets',),
            'cogs.engagement': ('cogs.engagement.advanced_polls', 'cogs.engagement.minigames'),
            'cogs.suggestions': ('cogs.engagement.suggestions',),
            'cogs.trust': ('cogs.moderation.trust_score',),
            'cogs.audit_log': ('cogs.moderation.audit_log',),
            'cogs.welcome': ('cogs.community.welcome', 'cogs.community.autorole'),
            'cogs.social_updates': ('cogs.social.delivery',),
        }
        expected_extensions = [target for old in baseline['extensions'] for target in relocation[old]]
        self.assertEqual(list(BOT_EXTENSIONS), expected_extensions + ['cogs.community.applications','cogs.moderation.appeals','cogs.engagement.scheduled_messages','cogs.engagement.starboard','cogs.engagement.giveaways'])
        self.assertEqual([item.id for item in FEATURES], [item['id'] for item in baseline['features']] + ['applications','appeals','scheduled_messages','starboard','giveaways'])
        for actual, expected in zip(FEATURES, baseline['features']):
            for key, value in expected.items():
                if key == 'docs_files':
                    for path in value:
                        self.assertTrue((ROOT / path).is_file(), path)
                    continue
                result = getattr(actual, key)
                if actual.id == 'suggestions' and key == 'fields':
                    self.assertEqual(result.count('discussion_enabled'), 1)
                    result = tuple(field for field in result if field not in {'discussion_enabled','categories','tags','retention_days'})
                self.assertEqual(list(result) if isinstance(result, tuple) else result, value, (actual.id, key))
        self.assertEqual({item.id for item in REGISTRY.features if not item.dashboard}, {'echo', 'calculate', 'roll', 'gemini'})

    def test_duplicate_categories_features_and_invalid_category_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'maturity'):
            catalog(replace(feature(), maturity='unknown'))
        for maturity in ('stable','improving','unavailable'):
            self.assertEqual(catalog(replace(feature(),maturity=maturity)).features[0].maturity,maturity)
        with self.assertRaisesRegex(ValueError, 'category'):
            Registry((Category('example', 'nav.example', ()), Category('example', 'nav.other', ())))
        with self.assertRaisesRegex(ValueError, 'duplicate feature'):
            catalog(feature(), feature())
        with self.assertRaisesRegex(ValueError, 'Unregistered category'):
            catalog(replace(feature(), category='other'))
        with self.assertRaisesRegex(ValueError, 'Invalid or duplicate feature'):
            catalog(feature('../escape'))

    def test_unknown_self_cyclic_and_cross_category_parents_are_rejected(self):
        for items, message in [((feature(parent='missing'),), 'Unknown parent'),
                               ((feature(parent='sample'),), 'Cyclic'),
                               ((feature('first', parent='second'), feature('second', parent='first')), 'Cyclic')]:
            with self.subTest(items=items), self.assertRaisesRegex(ValueError, message):
                catalog(*items)
        with self.assertRaisesRegex(ValueError, 'another category'):
            Registry((Category('example', 'nav.example', (feature(parent='foreign'),)),
                      Category('other', 'nav.other', (Feature('foreign', 'other', dashboard=False),))))

    def test_metadata_fields_docs_and_bindings_are_validated(self):
        with self.assertRaisesRegex(ValueError, 'Incomplete dashboard'):
            catalog(replace(feature(), dashboard=True))
        with self.assertRaisesRegex(ValueError, 'Invalid fields'):
            catalog(feature(required_fields=('absent',)))
        duplicate_doc = replace(FEATURES[0], id='duplicate')
        with self.assertRaisesRegex(ValueError, 'Duplicate feature documentation'):
            Registry((Category('community', 'nav.community', (FEATURES[0], replace(duplicate_doc, bindings=()))),))
        binding = Binding('sample', 'api', 'example:factory')
        for bindings, message in [((binding, binding), 'duplicate binding'),
                                   ((binding, replace(binding, id='other')), 'Duplicate runtime'),
                                   ((replace(binding, process='invalid'),), 'Invalid binding'),
                                   ((replace(binding, target='../bad'),), 'Invalid binding')]:
            with self.subTest(bindings=bindings), self.assertRaisesRegex(ValueError, message):
                catalog(bindings=bindings)

    def test_factories_are_resolved_only_for_selected_process_and_not_called(self):
        api = Mock()
        worker = Mock()
        registry = catalog(bindings=(Binding('api', 'api', 'example_api:create'),
                                     Binding('worker', 'worker', 'example_worker:main')))
        with patch('features.loading.import_module', return_value=SimpleNamespace(create=api)) as imported:
            self.assertEqual(resolve_bindings(registry.for_process('api')), (api,))
        imported.assert_called_once_with('example_api')
        api.assert_not_called()
        worker.assert_not_called()

    def test_missing_noncallable_and_wrong_async_loaders_are_rejected(self):
        for module, message in [(SimpleNamespace(), 'Cannot resolve'),
                                (SimpleNamespace(factory=1), 'not callable')]:
            with patch('features.loading.import_module', return_value=module), self.assertRaisesRegex(ValueError, message):
                resolve_bindings((Binding('bad', 'api', 'example:factory'),))
        with patch('features.loading.import_module', side_effect=ModuleNotFoundError), self.assertRaisesRegex(ValueError, 'Cannot resolve'):
            resolve_bindings((Binding('bad', 'api', 'missing:factory'),))
        with patch('features.loading.import_module', return_value=SimpleNamespace(setup=lambda bot: None)), self.assertRaisesRegex(ValueError, 'must be async'):
            validate_extensions(('example',))
        async def async_factory(): pass
        with patch('features.loading.import_module', return_value=SimpleNamespace(factory=async_factory)), self.assertRaisesRegex(ValueError, 'synchronous'):
            resolve_bindings((Binding('bad', 'api', 'example:factory'),))

    def test_duplicate_extensions_are_rejected_before_factory_invocation(self):
        async def setup(bot): raise AssertionError('must not be called')
        with patch('features.loading.import_module', return_value=SimpleNamespace(setup=setup)), self.assertRaisesRegex(ValueError, 'Duplicate runtime'):
            validate_extensions(('example', 'example'))

    def test_fresh_metadata_import_has_no_framework_database_or_filesystem_effects(self):
        program = '''
import os, sys
sys.dont_write_bytecode = True
def audit(event, args):
    if event in ('socket.connect', 'os.mkdir'):
        raise AssertionError(event)
    if event == 'open' and isinstance(args[2], int) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
        raise AssertionError('write during import')
sys.addaudithook(audit)
from features.registry import REGISTRY
from features.defaults import ModuleSettingsAccess
assert len(REGISTRY.features) == 33
for name in ('discord', 'fastapi', 'psycopg', 'dashboard', 'cogs', 'config', 'database'):
    assert name not in sys.modules, name
'''
        result = subprocess.run([sys.executable, '-c', program], cwd=ROOT, text=True, capture_output=True,
                                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_domains_do_not_import_registry_and_feature_declarations_do_not_import_adapters(self):
        for folder in ('moderation', 'ticketing', 'reaction_roles', 'social', 'suggestions', 'community', 'engagement', 'guild_settings', 'applications', 'appeals', 'scheduling', 'starboard', 'giveaways', 'features'):
            for path in (ROOT / folder).rglob('*.py'):
                for node in ast.walk(ast.parse(path.read_text())):
                    modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ''] if isinstance(node, ast.ImportFrom) else []
                    for module in modules:
                        if folder == 'features':
                            self.assertNotIn(module.split('.')[0], {'cogs', 'dashboard', 'discord', 'fastapi', 'database', 'config'}, str(path))
                        else:
                            self.assertNotEqual(module.split('.')[0], 'features', str(path))

    def test_default_settings_copy_and_normalizer_override_preserve_revision_contract(self):
        raw = {'enabled': False, 'revision': 4, 'settings': {'values': [1]}}
        store = Mock()
        store.get_module.return_value = raw
        access = ModuleSettingsAccess(store, 'sample')
        access.read(7)['settings']['values'].append(2)
        self.assertEqual(raw['settings']['values'], [1])
        def normalize(value):
            value['values'].append(3)
            return value
        overridden = ModuleSettingsAccess(store, 'sample', normalize)
        overridden.save(7, enabled=True, settings=raw['settings'], expected_revision=4)
        store.set_module.assert_called_once_with(7, 'sample', enabled=True, settings={'values': [1, 3]}, expected_revision=4)
        self.assertEqual(raw['settings']['values'], [1])
        store.set_module.side_effect = RuntimeError('revision_conflict')
        with self.assertRaisesRegex(RuntimeError, 'revision_conflict'):
            access.save(7, enabled=True, settings={}, expected_revision=3)


class ApiRegistrationTests(unittest.TestCase):
    def router(self, path='/example/{item}', method='GET', operation_id=None):
        from fastapi import APIRouter
        router = APIRouter()
        async def endpoint(): return {}
        router.add_api_route(path, endpoint, methods=[method], operation_id=operation_id)
        return router

    def test_route_shapes_and_operation_ids_collide_but_methods_do_not(self):
        from dashboard.api.composition import build_routers
        first = lambda context: self.router()
        with self.assertRaisesRegex(ValueError, 'Duplicate API route'):
            build_routers((first, lambda context: self.router('/example/{other}')), None)
        with self.assertRaisesRegex(ValueError, 'operation ID'):
            build_routers((lambda context: self.router('/a', operation_id='same'),
                           lambda context: self.router('/b', operation_id='same')), None)
        self.assertEqual(len(build_routers((first, lambda context: self.router(method='POST')), None)), 2)
        with self.assertRaisesRegex(ValueError, 'APIRouter'):
            build_routers((lambda context: None,), None)

    def test_one_context_and_one_factory_call_per_application(self):
        from dashboard.api_v1 import create_api_router
        first, second = object(), object()
        factory = Mock(side_effect=lambda context: self.router())
        with patch('dashboard.api_v1.resolve_bindings', return_value=(factory,)), \
             patch('dashboard.api_v1.create_context', side_effect=(first, second)) as contexts:
            create_api_router('first', object())
            create_api_router('second', object())
        self.assertEqual(contexts.call_count, 2)
        self.assertEqual([call.args[0] for call in factory.call_args_list], [first, second])

    def test_invalid_loader_stops_before_context_initialization(self):
        from dashboard.api_v1 import create_api_router
        with patch('dashboard.api_v1.resolve_bindings', side_effect=ValueError('missing loader')), \
             patch('dashboard.api_v1.create_context') as context, self.assertRaisesRegex(ValueError, 'missing loader'):
            create_api_router('unused', object())
        context.assert_not_called()
