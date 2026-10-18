from guild_settings import GuildSettingsRepository
from db_support import prepare_database
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from fastapi.staticfiles import StaticFiles


class DashboardRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        env = {'DISCORD_TOKEN': 'test-token', 'DISCORD_CLIENT_ID': '1', 'DISCORD_CLIENT_SECRET': 'test-secret',
               'DISCORD_REDIRECT_URI': 'http://testserver/oauth/callback', 'SESSION_SECRET': 'test-session-secret',
               'DASHBOARD_HTTPS_ONLY': 'false', 'DATABASE_URL': str(prepare_database(root / 'test.db', self.addCleanup)), 'DATA_DIR': str(root),
               'TUEKA_ENV': 'stage', 'TUEKA_API_DOCS_ENABLED': 'false',
               'DASHBOARD_UI_V2': 'false', 'DASHBOARD_UI_V2_GUILDS': '999',
               'TICKETS_V2': 'false', 'TICKETS_V2_GUILDS': 'retired-allowlist'}
        with patch.dict(os.environ, env):
            spec = importlib.util.spec_from_file_location('dashboard_routes_test', 'dashboard/app.py')
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
        self.module.FRONTEND_DIST = root / 'ui'
        self.module.FRONTEND_DIST.mkdir()
        (self.module.FRONTEND_DIST / 'index.html').write_text('<html>SPA shell</html>')
        self.module.api.bot_user = AsyncMock(return_value={'id': '1', 'username': 'Tueka', 'avatar': None})
        self.module.api.current_user = AsyncMock(return_value={'id': '2', 'username': 'User'})
        self.module.api.exchange_code = AsyncMock(return_value={'access_token': 'test-access', 'expires_in': 3600})
        self.module.api.can_manage = AsyncMock(return_value=False)
        self.client = TestClient(self.module.app, follow_redirects=False)
        self.addCleanup(self.client.close)

    def test_current_spa_routes_ignore_retired_flags_and_revalidate_assets(self):
        for path in ['/servers', '/servers/1', '/servers/1/settings', '/servers/1/modules/welcome',
                     '/servers/1/social', '/servers/1/social/youtube', '/servers/1/moderation/automod/rules/new',
                     '/servers/1/tickets/inbox/123', '/servers/1/tickets/panels/2', '/servers/1/reaction-roles/new',
                     '/servers/1/suggestions', '/servers/1/applications', '/servers/1/applications/review',
                     '/servers/1/applications/settings', '/servers/1/appeals', '/servers/1/appeals/settings',
                     '/servers/1/schedules', '/servers/1/schedules/settings', '/servers/1/insights', '/servers/1/insights/settings', '/tickets/transcripts/token']:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn('SPA shell', response.text)
                self.assertIn('no-cache', response.headers['cache-control'])
                self.assertIn('app;dur=', response.headers['server-timing'])

    def test_missing_assets_fail_explicitly_and_old_urls_are_gone(self):
        (self.module.FRONTEND_DIST / 'index.html').unlink()
        self.assertEqual(self.client.get('/servers').status_code, 503)
        for path in ['/servers/1/automod', '/servers/1/modules/reaction_roles', '/servers/1/modules/unknown',
                     '/servers/1/moderation/automod/rules/1.json', '/servers/1/modules/applications',
                     '/servers/1/applications/unknown', '/servers/1/applications/review/1.json']:
            self.assertEqual(self.client.get(path).status_code, 404, path)
        for path in ['/servers/1/modules/welcome', '/servers/1/automod/settings', '/servers/1/social/subscriptions',
                     '/servers/1/moderation/settings']:
            self.assertIn(self.client.post(path).status_code, (404, 405), path)

    def test_oauth_session_guild_denial_logout_and_state_replay(self):
        self.assertEqual(self.client.get('/api/v1/session').status_code, 401)
        login = self.client.get('/login')
        state = parse_qs(urlparse(login.headers['location']).query)['state'][0]
        callback = self.client.get('/oauth/callback', params={'code': 'code', 'state': state})
        self.assertEqual(callback.status_code, 303)
        self.assertEqual(callback.headers['location'], '/servers')
        self.assertEqual(self.client.get('/api/v1/session').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/guilds/1/suggestions/items').status_code, 403)
        self.assertEqual(self.client.get('/oauth/callback', params={'code': 'code', 'state': state}).status_code, 400)
        self.assertEqual(self.client.get('/logout').status_code, 303)
        self.assertEqual(self.client.get('/api/v1/session').status_code, 401)

    def test_public_landing_and_not_found_survive(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/unknown').status_code, 404)
        self.assertEqual(self.client.get('/static/landing-v2.css').status_code, 200)
        self.assertEqual(self.client.get('/api/openapi.json').status_code, 404)
        self.assertEqual(self.client.get('/api/docs').status_code, 404)

    def test_api_docs_require_explicit_development_environment(self):
        for environment, enabled, expected in [('dev', 'true', 200), ('dev', 'false', 404), ('stage', 'true', 404), ('prod', 'true', 404), ('', 'true', 404)]:
            with self.subTest(environment=environment, enabled=enabled), patch.dict(os.environ, {
                'TUEKA_ENV': environment, 'TUEKA_API_DOCS_ENABLED': enabled,
                'DATABASE_URL': self.module.settings.database_url, 'DISCORD_CLIENT_ID': '1',
                'DISCORD_CLIENT_SECRET': 'offline', 'DISCORD_REDIRECT_URI': 'http://testserver/oauth/callback',
                'SESSION_SECRET': 'offline', 'DISCORD_TOKEN': 'offline',
            }):
                spec = importlib.util.spec_from_file_location('api_docs_test', 'dashboard/app.py')
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                client = TestClient(module.app, follow_redirects=False)
                self.addCleanup(client.close)
                for path in ('/api/docs', '/api/openapi.json'):
                    self.assertEqual(client.get(path).status_code, expected)

    def test_social_oauth_rejects_missing_csrf_and_retires_old_form_url(self):
        response = self.client.post('/social/oauth/tiktok/connect/1')
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], '/servers/1/social/tiktok?error=csrf')
        self.module.api.can_manage.assert_not_awaited()
        self.assertIn(self.client.post('/servers/1/social/connect/tiktok').status_code, (404, 405))

    def login(self):
        login = self.client.get('/login')
        state = parse_qs(urlparse(login.headers['location']).query)['state'][0]
        self.client.get('/oauth/callback', params={'code': 'code', 'state': state})
        return self.client.get('/api/v1/session').json()['csrf_token']

    def test_ticket_api_ignores_flags_but_preserves_auth_csrf_and_revision(self):
        url = '/api/v1/guilds/1/tickets/settings'
        self.assertEqual(self.client.get(url).status_code, 401)
        csrf = self.login()
        self.assertEqual(self.client.get(url).status_code, 403)
        self.module.api.can_manage.return_value = True
        self.module.api.guild_resources = AsyncMock(return_value=([], [], 8))
        value = self.client.get(url).json()
        self.assertFalse(value['enabled'])
        self.assertEqual(value['revision'], 0)
        value['open_limit'] = 3
        self.assertEqual(self.client.put(url, json=value).status_code, 403)
        missing = {key: item for key, item in value.items() if key != 'revision'}
        self.assertEqual(self.client.put(url, json=missing, headers={'x-csrf-token': csrf}).status_code, 422)
        saved = self.client.put(url, json=value, headers={'x-csrf-token': csrf})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(self.client.get(url).json()['open_limit'], 3)
        self.assertEqual(self.client.put(url, json=value, headers={'x-csrf-token': csrf}).status_code, 409)
        self.assertEqual(self.client.put('/api/v1/guilds/1/modules/tickets', json={}, headers={'x-csrf-token': csrf}).status_code, 404)
        features = self.client.get('/api/v1/guilds/1/features').json()['items']
        ticket = next(item for item in features if item['id'] == 'tickets')
        self.assertEqual(ticket['revision'], saved.json()['revision'])
        self.assertEqual(ticket['settings']['open_limit'], 3)

    def test_ticket_staff_guild_visibility_without_allowlist(self):
        from ticketing import TicketRepository
        repository = TicketRepository(prepare_database(self.module.settings.database_url, self.addCleanup))
        repository.save_team(1, {'name': 'Staff', 'user_ids': [2]})
        self.login()
        self.module.api.user_guilds = AsyncMock(return_value=[{'id': '1', 'name': 'Support', 'permissions': '0'}, {'id': '3', 'name': 'Other', 'permissions': '0'}])
        self.module.api.bot_guild_ids = AsyncMock(return_value={1, 3})
        self.module.api.guild_member = AsyncMock(return_value={'roles': []})
        response = self.client.get('/api/v1/guilds')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['items'], [{'id': '1', 'name': 'Support', 'icon': None, 'access': 'ticket_staff'}])
        self.assertEqual(self.client.get('/api/v1/guilds/1/tickets').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/guilds/3/tickets').status_code, 403)

    def test_reaction_roles_uses_only_v2_settings_and_omits_legacy_contract(self):
        GuildSettingsRepository(self.module.settings.database_url).set_module(1, 'reaction_roles', enabled=True, settings={'reaction_role_ids': [123]})
        url = '/api/v1/guilds/1/reaction-roles'
        self.assertEqual(self.client.get(url).status_code, 401)
        csrf = self.login()
        self.assertEqual(self.client.get(url).status_code, 403)
        self.module.api.can_manage.return_value = True
        self.module.api.guild_resources = AsyncMock(return_value=([], [], 8))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn('legacy', response.json())
        settings = response.json()['settings']
        self.assertFalse(settings['enabled'])
        settings['enabled'] = True
        self.assertEqual(self.client.put(url + '/settings', json=settings).status_code, 403)
        saved = self.client.put(url + '/settings', json=settings, headers={'x-csrf-token': csrf})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(self.client.put(url + '/settings', json=settings, headers={'x-csrf-token': csrf}).status_code, 409)
        self.assertEqual(self.client.put('/api/v1/guilds/1/modules/reaction_roles', json={}, headers={'x-csrf-token': csrf}).status_code, 404)
        features = self.client.get('/api/v1/guilds/1/features').json()['items']
        feature = next(item for item in features if item['id'] == 'reaction_roles')
        self.assertEqual(feature['revision'], saved.json()['revision'])
        self.assertEqual(feature['fields'], [])
        self.assertNotIn('reaction_role_ids', feature['settings'])

    def test_built_ui_and_documentation_assets_are_served(self):
        root = Path(self.temp.name)
        for prefix in ('ui', 'docs'):
            directory = root / prefix
            directory.mkdir(exist_ok=True)
            (directory / 'index.html').write_text(f'{prefix} index')
            (directory / 'assets').mkdir()
            (directory / 'assets' / 'app.js').write_text('/* asset */')
            mount = next(route for route in self.module.app.routes if getattr(route, 'path', None) == f'/{prefix}')
            files = self.module.DocumentationFiles if prefix == 'docs' else StaticFiles
            mount.app = files(directory=directory, html=True)
        response = self.client.get('/docs/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('frame-ancestors', response.headers['content-security-policy'])
        self.assertIn('immutable', self.client.get('/docs/assets/app.js').headers['cache-control'])
        self.assertEqual(self.client.get('/ui/assets/app.js').status_code, 200)

    def test_documentation_clean_urls_serve_only_existing_html_files(self):
        directory = Path(self.temp.name) / 'docs'
        for language in ('', 'en'):
            page = directory / language / 'features' / 'insights.html'
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text('<h1>Insights proof</h1>')
        (directory.parent / 'outside.html').write_text('private outside root')
        mount = next(route for route in self.module.app.routes if getattr(route, 'path', None) == '/docs')
        mount.app = self.module.DocumentationFiles(directory=directory, html=True)
        for language in ('', 'en/'):
            url = '/docs/' + language + 'features/insights'
            for method in (self.client.get, self.client.head):
                response = method(url)
                self.assertEqual(response.status_code, 200)
                self.assertIn('text/html', response.headers['content-type'])
            self.assertIn('Insights proof', self.client.get(url).text)
            self.assertEqual(self.client.get(url + '.html').status_code, 200)
        for url in ('/docs/features/missing', '/docs/features/insights.json',
                    '/docs/%2e%2e/outside', '/docs/features/missing.js'):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        self.assertEqual(self.client.post('/docs/features/insights').status_code, 405)
