"""Architecture gates, including adversarial imports to prove the gate works."""
import ast
from importlib.util import resolve_name
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = {'community', 'engagement', 'guild_settings', 'moderation', 'ticketing',
           'reaction_roles', 'social', 'suggestions', 'applications', 'appeals', 'scheduling', 'starboard', 'giveaways'}
SHARED = {'database', 'jobs', 'discord_io'}
CATEGORIES = {p.parent.name for p in (ROOT / 'features').glob('*/registry.py')}
LAYERS = ('features', 'cogs', 'guild_settings', 'dashboard.api')
# Explicit external presentation/IO adapters, not Domain logic.
ADAPTERS = {f'{name}.discord_adapter' for name in DOMAINS} | {'suggestions.presentation'}
EXTERNAL = ADAPTERS | {'social.providers', 'social.worker'}


def external(module):
    return any(module == adapter or module.startswith(adapter + '.') for adapter in EXTERNAL)


def imports(module, source):
    package = module.removesuffix('.__init__') if module.endswith('.__init__') else module.rpartition('.')[0]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            target = '.' * node.level + (node.module or '')
            target = resolve_name(target, package) if node.level else target
            yield target
            for alias in node.names:
                yield target + '.' + alias.name
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            if ast.unparse(node.func) in {'import_module', 'importlib.import_module', '__import__'} and isinstance(node.args[0].value, str):
                target = node.args[0].value
                yield resolve_name(target, package) if target.startswith('.') else target


def category(module):
    for layer in LAYERS:
        if module.startswith(layer + '.'):
            value = module[len(layer) + 1:].split('.')[0]
            if value in CATEGORIES:
                return value
    return None


def violations(module, source):
    failures = []
    owner = module.split('.')[0]
    for target in imports(module, source):
        root = target.split('.')[0]
        if owner in DOMAINS and not external(module):
            if root in {'discord', 'fastapi', 'starlette', 'httpx', 'requests', 'aiohttp', 'dashboard', 'cogs', 'features'} or external(target):
                failures.append(f'Domain adapter dependency: {module} -> {target}')
        if owner in SHARED and root in DOMAINS | {'features', 'cogs', 'dashboard'}:
            failures.append(f'Shared reverse dependency: {module} -> {target}')
        if owner == 'features' and root in DOMAINS | SHARED | {'cogs', 'dashboard', 'discord', 'fastapi', 'starlette', 'config'}:
            failures.append(f'Declaration runtime dependency: {module} -> {target}')
        if category(module) and category(target) and category(module) != category(target):
            failures.append(f'Cross-category internal dependency: {module} -> {target}')
        if module.startswith('dashboard.api.') and not category(module) and category(target):
            failures.append(f'Shared API reverse dependency: {module} -> {target}')
    return failures


class FeatureBoundaryTests(unittest.TestCase):
    def test_current_backend_dependency_boundaries(self):
        failures = []
        for folder in sorted(DOMAINS | SHARED | {'features', 'cogs', 'dashboard/api'}):
            for path in (ROOT / folder).rglob('*.py'):
                module = '.'.join(path.relative_to(ROOT).with_suffix('').parts)
                failures.extend(violations(module, path.read_text(encoding='utf-8')))
        self.assertEqual(failures, [])

    def test_gate_rejects_absolute_relative_reexport_and_dynamic_imports(self):
        cases = [
            ('ticketing.service', 'import discord as sdk'),
            ('ticketing.repository', 'from fastapi import Request'),
            ('ticketing.service', 'import httpx'),
            ('social.service', 'from .providers.registry import build_adapters'),
            ('ticketing.service', 'from . import discord_adapter'),
            ('ticketing.__init__', 'from .discord_adapter import *'),
            ('jobs.runner', 'from ticketing import TicketRepository'),
            ('database.connections', 'importlib.import_module("features.registry")'),
            ('features.community.example', 'from cogs.community import welcome'),
            ('cogs.community.example', 'from ..moderation import runtime'),
            ('dashboard.api.community.example', 'from guild_settings.moderation import automod'),
            ('dashboard.api.session', 'from .community.ticket_support.dependencies import team_member'),
        ]
        for module, source in cases:
            with self.subTest(module=module, source=source):
                self.assertTrue(violations(module, source))

    def test_gate_allows_owned_implementation_and_explicit_shared_contracts(self):
        for module, source in [
            ('ticketing.service', 'from discord_io import DiscordFailure'),
            ('ticketing.service', 'from .contracts import TicketResourcePort'),
            ('ticketing.discord_adapter', 'import discord'),
            ('social.providers.youtube', 'import httpx'),
            ('social.worker', 'from .providers.registry import build_adapters'),
            ('cogs.community.example', 'from guild_settings.community import welcome'),
            ('features.registry', 'from .community.registry import CATEGORY'),
            ('dashboard.api.session', 'from ticketing.access import team_member'),
        ]:
            self.assertEqual(violations(module, source), [])
