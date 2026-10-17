"""Public API contracts captured before the P2-5 router split."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api_support import ApiFixture
from moderation import default_rule
from ticketing import TicketRepository
from social import SocialRepository
from reaction_roles.repository import ReactionRoleRepository


CONTRACT = Path(__file__).parent / 'fixtures' / 'api_v1_contract.json'
U4_PATHS = {
    '/api/v1/guilds/{guild_id}/moderation/{family}/rules/state': 'put',
    '/api/v1/guilds/{guild_id}/moderation/{family}/templates/{trigger_type}': 'get',
    '/api/v1/guilds/{guild_id}/suggestions/items/{suggestion_id}/events': 'get',
    '/api/v1/guilds/{guild_id}/suggestions/items/{suggestion_id}/review': 'post',
}
APPLICATION_PATHS = {
    '/api/v1/guilds/{guild_id}/applications/forms': {'get','post'},
    '/api/v1/guilds/{guild_id}/applications/forms/{form_id}': {'put'},
    '/api/v1/guilds/{guild_id}/applications/items': {'get'},
    '/api/v1/guilds/{guild_id}/applications/items/{item_id}/events': {'get'},
    '/api/v1/guilds/{guild_id}/applications/items/{item_id}/review': {'post'},
}
APPEAL_PATHS = {
    '/api/v1/guilds/{guild_id}/appeals/items': {'get'},
    '/api/v1/guilds/{guild_id}/appeals/items/{item_id}': {'get'},
    '/api/v1/guilds/{guild_id}/appeals/items/{item_id}/reply': {'post'},
    '/api/v1/guilds/{guild_id}/appeals/items/{item_id}/review': {'post'},
    '/api/v1/guilds/{guild_id}/appeals/items/{item_id}/ticket': {'post'},
    '/api/v1/guilds/{guild_id}/appeals/items/{item_id}/delivery/{job_id}/retry': {'post'},
}
ADDED_PATHS = {**{path:{method} for path,method in U4_PATHS.items()},**APPLICATION_PATHS,**APPEAL_PATHS}


def request_path(template):
    values = {'guild_id': '1', 'module_id': 'welcome', 'provider': 'youtube', 'family': 'automod'}
    import re
    return re.sub(r'\{([^}]+)\}', lambda match: values.get(match[1], '1'), template)


def boundary_responses(fixture):
    rows = []
    routes = [(path, method.upper()) for path, operations in fixture.app.openapi()['paths'].items()
              for method in operations if method in {'get', 'post', 'put', 'delete', 'patch'}]
    for mode in ('anonymous', 'forbidden', 'csrf'):
        fixture.session = {} if mode == 'anonymous' else {'session_id': 'session', 'csrf_token': 'csrf'}
        fixture.discord.can_manage.return_value = mode == 'csrf'
        fixture.discord.guild_member.return_value = None
        for path, method in routes:
            if mode == 'csrf' and method == 'GET':
                continue
            response = fixture.client.request(method, request_path(path), json={},
                headers={'x-csrf-token': 'csrf'} if mode == 'forbidden' else {})
            rows.append({'mode': mode, 'method': method, 'path': path,
                         'status': response.status_code, 'body': response.json() if response.content else None})
    return sorted(rows, key=lambda row: (row['mode'], row['path'], row['method']))


class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.api = ApiFixture(Path(self.temp.name), self.addCleanup)
        self.addCleanup(self.api.client.close)

    def test_openapi_paths_parameters_statuses_and_shapes_are_preserved(self):
        expected = json.loads(CONTRACT.read_text(encoding='utf-8'))
        actual = self.api.app.openapi()['paths']
        baseline = expected['openapi']['paths']
        self.assertEqual(set(actual), set(baseline) | set(ADDED_PATHS))
        for path, methods in ADDED_PATHS.items():
            self.assertEqual(set(actual[path]), methods)
        for path, methods in baseline.items():
            self.assertEqual(set(actual[path]), set(methods))
            for method, operation in methods.items():
                current = actual[path][method]
                for key in ('operationId', 'parameters'):
                    self.assertEqual(current.get(key), operation.get(key), (path, method, key))
                self.assertTrue(set(operation['responses']).issubset(current['responses']))

    def test_all_route_authentication_authorization_and_csrf_boundaries_are_preserved(self):
        expected = json.loads(CONTRACT.read_text(encoding='utf-8'))
        from dashboard.api.route import error_detail
        baseline = expected['boundaries']
        for row in baseline:
            if row['status'] >= 400:
                row['body'] = {'detail': error_detail(row['status'], row['body']['detail'])}
            elif isinstance(row['body'], dict) and 'items' in row['body']:
                row['body'] = {'next': None, **row['body']}
        actual = boundary_responses(self.api)
        self.assertEqual([row for row in actual if row['path'] not in ADDED_PATHS], baseline)
        added = [row for row in actual if row['path'] in ADDED_PATHS]
        self.assertEqual(len(added), 41)
        for row in added:
            # CSRF runs before authentication on writes, as for existing routes.
            expected_code = ('csrf_invalid' if row['method'] in {'PUT', 'POST'} and row['mode'] != 'forbidden'
                             else 'authentication_required' if row['mode'] == 'anonymous' else 'guild_forbidden')
            self.assertEqual(row['body']['detail']['code'], expected_code, row)
            self.assertEqual(row['status'], 401 if expected_code == 'authentication_required' else 403)

    def test_social_save_conflict_cross_guild_and_delete_contract(self):
        root = '/api/v1/guilds/1/social/youtube/subscriptions'
        value = {'account': 'UC' + 'a' * 22, 'channel_id': '10', 'events': ['video']}
        created = self.api.client.post(root, json=value, headers=self.api.headers)
        self.assertEqual(created.status_code, 201, created.text)
        item = created.json()
        self.assertEqual((item['guild_id'], item['channel_id']), ('1', '10'))
        url = root + '/' + str(item['id'])
        self.assertEqual(self.api.client.put(url, json={**value, 'revision': 999}, headers=self.api.headers).status_code, 409)
        foreign = url.replace('/guilds/1/', '/guilds/2/')
        self.assertEqual(self.api.client.delete(foreign, headers=self.api.headers).status_code, 404)
        response = self.api.client.delete(url, headers={**self.api.headers, 'if-match': str(item['revision'])})
        self.assertEqual((response.status_code, response.content), (204, b''))
        self.assertEqual(self.api.client.get(root).json()['items'], [])

    def test_social_preview_is_side_effect_free_and_retry_preserves_cursor(self):
        root = '/api/v1/guilds/1/social/youtube'
        value = {'account': 'UC' + 'a' * 22, 'channel_id': '10', 'events': ['video']}
        saved = self.api.client.post(root + '/subscriptions', json=value, headers=self.api.headers).json()
        repository = SocialRepository(self.api.database)
        target = repository.claim_social_targets('fixture')[0]
        repository.complete_social_target(target['id'], target['lease_owner'], status='degraded',
            cursor={'seen': ['old']}, next_check_at=10 ** 12, error='fixture failure')
        before = repository.social_target(target['id'])
        preview = self.api.client.post(root + '/preview', json={'event': 'video', 'template': {'title': '{account}: {title}'}}, headers=self.api.headers)
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertIn('Sample Creator', preview.json()['title'])
        self.assertEqual(repository.social_target(target['id']), before)
        self.assertEqual(repository.pending_social_events(), [])
        retry = root + '/subscriptions/' + str(saved['id']) + '/retry'
        self.assertEqual(self.api.client.post(retry).status_code, 403)
        self.assertEqual(self.api.client.post(retry.replace('/guilds/1/', '/guilds/2/'), headers=self.api.headers).status_code, 404)
        self.assertEqual(repository.social_target(target['id']), before)
        self.assertEqual(self.api.client.post(retry, headers=self.api.headers).status_code, 200)
        after = repository.social_target(target['id'])
        self.assertEqual((after['status'], after['next_check_at'], after['cursor']), ('pending', 0, {'seen': ['old']}))
        self.assertEqual(repository.pending_social_events(), [])

    def _deleted_reaction_role(self):
        from test_reaction_roles import message
        root = '/api/v1/guilds/1/reaction-roles'
        created = self.api.client.post(root, json=message(role_id=500), headers=self.api.headers)
        self.assertEqual(created.status_code, 201, created.text)
        repository = ReactionRoleRepository(self.api.database)
        repository.set_discord_message(created.json()['id'], 900)
        repository.delete_message(1, created.json()['id'], recoverable=True)
        return repository, root + '/recoveries/900/restore'

    def test_reaction_role_restore_consumes_one_snapshot_and_is_guild_scoped(self):
        repository, url = self._deleted_reaction_role()
        body = {'channel_id': '10', 'message_id': '900'}
        self.assertEqual(self.api.client.post(url.replace('/guilds/1/', '/guilds/2/'), json=body, headers=self.api.headers).status_code, 404)
        with patch.object(ReactionRoleRepository, 'restore_message', side_effect=RuntimeError('recovery_conflict')):
            self.assertEqual(self.api.client.post(url, json=body, headers=self.api.headers).status_code, 409)
        self.assertIsNotNone(repository.recovery(1, 900))
        restored = self.api.client.post(url, json=body, headers=self.api.headers)
        self.assertEqual(restored.status_code, 201, restored.text)
        self.assertEqual(restored.json()['source'], 'external')
        self.assertEqual(restored.json()['message_id'], '900')
        self.assertIsNone(repository.recovery(1, 900))
        self.assertEqual(self.api.client.post(url, json=body, headers=self.api.headers).status_code, 404)
        self.assertEqual(len(repository.messages(1)), 1)

    def test_reaction_role_restore_snapshot_failure_rolls_back_configuration_and_audit(self):
        repository, url = self._deleted_reaction_role()
        before = repository.events(1)
        with patch.object(ReactionRoleRepository, 'consume_recovery', side_effect=RuntimeError('fixture consume failure')):
            with self.assertRaisesRegex(RuntimeError, 'fixture consume failure'):
                self.api.client.post(url, json={'channel_id': '10', 'message_id': '900'}, headers=self.api.headers)
        self.assertEqual(repository.messages(1), [])
        self.assertIsNotNone(repository.recovery(1, 900))
        self.assertEqual(repository.events(1), before)

    def test_reaction_role_restore_to_occupied_message_keeps_snapshot(self):
        from reaction_roles.service import ReactionRoleService
        from test_reaction_roles import message
        repository, url = self._deleted_reaction_role()
        ReactionRoleService(repository).create(1, {**message(role_id=500), 'source': 'external', 'message_id': 900})
        response = self.api.client.post(url, json={'channel_id': '10', 'message_id': '900'}, headers=self.api.headers)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()['detail']['code'], 'message_exists')
        self.assertIsNotNone(repository.recovery(1, 900))
        self.assertEqual(len(repository.messages(1)), 1)

    def test_moderation_rule_revision_and_guild_isolation(self):
        root = '/api/v1/guilds/1/moderation/automod/rules'
        value = {**default_rule('keyword'), 'name': 'Keyword', 'trigger_config': {'keywords': ['blocked']}}
        created = self.api.client.post(root, json=value, headers=self.api.headers)
        self.assertEqual(created.status_code, 201, created.text)
        item = created.json()
        url = root + '/' + str(item['id'])
        self.assertEqual(self.api.client.get(url).json(), item)
        self.assertEqual(self.api.client.put(url, json={**item, 'revision': 999}, headers=self.api.headers).status_code, 409)
        self.assertEqual(self.api.client.get(url.replace('/guilds/1/', '/guilds/2/')).status_code, 404)
        self.assertEqual(self.api.client.get(root).json()['items'], [item])

    def test_ticket_staff_access_is_limited_to_assigned_team_and_guild(self):
        repo = TicketRepository(self.api.database)
        repo.save_settings(1, {'enabled': True, 'open_limit': 5})
        team = repo.save_team(1, {'name': 'Staff', 'role_ids': [500]})
        other = repo.save_team(1, {'name': 'Other', 'role_ids': [501]})
        for index, selected in enumerate((team, other)):
            panel = repo.save_panel(1, {'name': selected['name'], 'mode': 'channel', 'category_id': 100, 'team_id': selected['id']})
            ticket = repo.reserve_ticket(1, panel['id'], 30 + index, 'open-' + str(index), {})
            repo.activate_ticket(ticket['id'], 200 + index, 100)
        self.api.discord.can_manage.return_value = False
        root = '/api/v1/guilds/1/tickets/items'
        response = self.api.client.get(root)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item['id'] for item in response.json()['items']], [1])
        self.assertEqual(self.api.client.get(root + '/2').status_code, 403)
        self.assertEqual(self.api.client.get('/api/v1/guilds/2/tickets/items/1').status_code, 403)
        self.assertEqual(self.api.client.put('/api/v1/guilds/1/tickets/settings', json={}, headers=self.api.headers).status_code, 403)

    def create_ticket(self, *, user_ids=None):
        repo = TicketRepository(self.api.database)
        repo.save_settings(1, {'enabled': True, 'open_limit': 5})
        team = repo.save_team(1, {'name': 'Staff', 'role_ids': [500], 'user_ids': user_ids or []})
        panel = repo.save_panel(1, {'name': 'Support', 'mode': 'channel', 'category_id': 100, 'team_id': team['id']})
        ticket = repo.reserve_ticket(1, panel['id'], 30, 'open-ticket', {})
        repo.activate_ticket(ticket['id'], 200, 100)
        return repo, ticket

    def test_reaction_roles_revision_headers_and_foreign_resources(self):
        from test_reaction_roles import message
        root = '/api/v1/guilds/1/reaction-roles'
        value = message(role_id=500)
        created = self.api.client.post(root, json=value, headers=self.api.headers)
        self.assertEqual(created.status_code, 201, created.text)
        item = created.json()
        url = root + '/messages/' + str(item['id'])
        self.assertEqual(self.api.client.get(url).json(), item)
        self.assertEqual(self.api.client.get(url.replace('/guilds/1/', '/guilds/2/')).status_code, 404)
        self.assertEqual(self.api.client.put(url, json={**value, 'revision': 999}, headers=self.api.headers).status_code, 409)
        self.assertEqual(self.api.client.post(url + '/move', json={'channel_id': 999, 'message_id': 900}, headers=self.api.headers).status_code, 422)
        self.api.discord.channel_message.assert_not_awaited()
        for header, status in ((None, 409), ('999', 409), ('invalid', 422)):
            with self.subTest(header=header):
                response = self.api.client.delete(url, headers={**self.api.headers, **({'if-match': header} if header else {})})
                self.assertEqual(response.status_code, status, response.text)
                self.assertEqual(self.api.client.get(url).json(), item)
        response = self.api.client.delete(url, headers={**self.api.headers, 'if-match': '"' + str(item['revision']) + '"'})
        self.assertEqual((response.status_code, response.content), (204, b''))

    def test_social_malformed_revision_does_not_delete_and_quoted_revision_works(self):
        root = '/api/v1/guilds/1/social/youtube/subscriptions'
        item = self.api.client.post(root, json={'account': 'UC' + 'a' * 22, 'channel_id': '10', 'events': ['video']}, headers=self.api.headers).json()
        url = root + '/' + str(item['id'])
        for revision, status in (('invalid', 422), ('999', 409)):
            response = self.api.client.delete(url, headers={**self.api.headers, 'if-match': revision})
            self.assertEqual(response.status_code, status)
            self.assertEqual(self.api.client.get(root).json()['items'], [item])
        self.assertEqual(self.api.client.delete(url, headers={**self.api.headers, 'if-match': '"' + str(item['revision']) + '"'}).status_code, 204)

    def test_removed_guild_member_cannot_use_explicit_ticket_team_assignment(self):
        repo, ticket = self.create_ticket(user_ids=[20])
        self.api.discord.can_manage.return_value = False
        self.api.discord.guild_member.return_value = None
        url = '/api/v1/guilds/1/tickets/items/' + str(ticket['id'])
        before = repo.outbox(ticket['id'])
        self.assertEqual(self.api.client.get(url).status_code, 403)
        self.assertEqual(self.api.client.post(url + '/reply', json={'content': 'blocked'}, headers=self.api.headers).status_code, 403)
        self.api.discord.can_manage.assert_awaited_with('token', 1, use_cache=False)
        self.api.discord.guild_member.assert_awaited_with(1, 20, use_cache=False)
        self.assertEqual(repo.outbox(ticket['id']), before)
        self.api.discord.user_guilds.return_value = [{'id': '1', 'name': 'Former guild', 'permissions': '0'}]
        self.assertEqual(self.api.client.get('/api/v1/guilds').json()['items'], [])

    def test_ticket_write_revalidates_team_membership_before_queueing(self):
        repo, ticket = self.create_ticket()
        self.api.discord.can_manage.return_value = False
        self.api.discord.guild_member.side_effect = [{'roles': ['500']}, {'roles': []}]
        response = self.api.client.post('/api/v1/guilds/1/tickets/items/' + str(ticket['id']) + '/reply',
            json={'content': 'blocked'}, headers=self.api.headers)
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(repo.outbox(ticket['id']), [])
        self.assertTrue(all(call.kwargs == {'use_cache': False} for call in self.api.discord.guild_member.await_args_list))

    def test_transcript_and_attachment_opener_assigned_staff_and_other_users(self):
        import asyncio
        import time
        from ticketing import TranscriptStorage
        repo, ticket = self.create_ticket()
        storage = TranscriptStorage(self.api.settings.data_dir / 'ticket-transcripts', self.api.settings.ticket_encryption_key)
        stored = asyncio.run(storage.save(1, ticket['id'], {'ticket': {**ticket, 'opened_at': 1}, 'close_reason': 'done', 'closed_at': 1, 'closed_by': 20, 'messages': [], 'attachments': []}))
        transcript = repo.save_transcript(ticket['id'], stored.backend, stored.object_key, stored.content_hash, stored.byte_size, int(time.time()) + 3600)
        blob = asyncio.run(storage.save_attachment(1, ticket['id'], 42, b'private file'))
        attachment = repo.save_attachment(ticket['id'], 42, 'test.txt', 'text/plain', blob.byte_size, blob.backend, blob.object_key, blob.content_hash)
        urls = ['/api/v1/tickets/transcripts/' + str(transcript['id']), '/api/v1/tickets/attachments/' + str(attachment['id'])]
        self.api.discord.can_manage.return_value = False
        for actor, member, status in ((30, None, 200), (20, {'roles': ['500']}, 200), (20, {'roles': ['501']}, 403), (20, None, 403)):
            self.api.discord.current_user.return_value = {'id': str(actor), 'username': 'Member'}
            self.api.discord.guild_member.return_value = member
            for url in urls:
                with self.subTest(actor=actor, member=member, url=url):
                    response = self.api.client.get(url)
                    self.assertEqual(response.status_code, status, response.text)
                    if status == 200 and 'attachments' in url:
                        self.assertEqual(response.content, b'private file')
                        self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
        self.api.session = {}
        for url in urls:
            self.assertEqual(self.api.client.get(url).status_code, 401)
        expired = repo.save_transcript(ticket['id'], stored.backend, stored.object_key, stored.content_hash, stored.byte_size, 1)
        self.assertEqual(self.api.client.get('/api/v1/tickets/transcripts/' + str(expired['id'])).status_code, 404)

    def test_domain_resource_rejections_do_not_save(self):
        from test_reaction_roles import message
        cases = [
            ('put', '/modules/welcome', {'settings': {'welcome_channel_id': '999'}, 'enabled': False}),
            ('put', '/suggestions/settings', {'settings': {'channel_id': '999'}, 'enabled': True, 'revision': 0}),
            ('post', '/social/youtube/subscriptions', {'account': 'UC' + 'a' * 22, 'channel_id': '999', 'events': ['video']}),
            ('post', '/reaction-roles', message(role_id=999)),
            ('put', '/tickets/settings', {'log_channel_id': '100'}),
        ]
        for method, path, body in cases:
            with self.subTest(path=path):
                response = self.api.client.request(method, '/api/v1/guilds/1' + path, json=body, headers=self.api.headers)
                self.assertEqual(response.status_code, 422, response.text)
                self.api.discord.guild_resources.assert_awaited_with(1, use_cache=False)
        self.assertEqual(self.api.client.get('/api/v1/guilds/1/social/youtube/subscriptions').json()['items'], [])
        self.assertEqual(self.api.client.get('/api/v1/guilds/1/reaction-roles').json()['items'], [])

    def test_application_dependencies_and_session_revocation_are_isolated(self):
        from dashboard.repository import DashboardRepository
        from guild_settings import GuildSettingsRepository
        other_root = Path(self.temp.name) / 'other'
        other_root.mkdir()
        other = ApiFixture(other_root, self.addCleanup)
        self.addCleanup(other.client.close)
        GuildSettingsRepository(self.api.database).set_module(1, 'welcome', enabled=True, settings={'welcome_content': 'First'})
        url = '/api/v1/guilds/1/modules/welcome'
        self.assertNotEqual(self.api.client.get(url).json(), other.client.get(url).json())
        self.api.session['session_id'] = 'unknown'
        self.assertEqual(self.api.client.get(url).status_code, 401)
        self.assertEqual(other.client.get(url).status_code, 200)
        other.discord.can_manage.return_value = False
        self.assertEqual(other.client.get(url).status_code, 403)
        self.api.session['session_id'] = 'session'
        self.assertEqual(self.api.client.get(url).status_code, 200)

    def test_domain_bot_permission_failures_do_not_persist_configuration(self):
        from test_reaction_roles import message
        self.api.discord.guild_resources.return_value = ([{'id': '10', 'type': 0, 'bot_permissions': '0'}, {'id': '100', 'type': 4}], [{'id': '500'}], 0)
        cases = [
            ('put', '/suggestions/settings', {'settings': {'channel_id': '10'}, 'enabled': True, 'revision': 0}),
            ('post', '/social/youtube/subscriptions', {'account': 'UC' + 'a' * 22, 'channel_id': '10', 'events': ['video']}),
            ('post', '/reaction-roles', message(role_id=500)),
        ]
        for method, path, body in cases:
            with self.subTest(path=path):
                response = self.api.client.request(method, '/api/v1/guilds/1' + path, json=body, headers=self.api.headers)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.api.client.get('/api/v1/guilds/1/social/youtube/subscriptions').json()['items'], [])
        self.assertEqual(self.api.client.get('/api/v1/guilds/1/reaction-roles').json()['items'], [])

    def test_expired_server_session_rejects_read_and_write(self):
        from dashboard.repository import DashboardRepository
        DashboardRepository(self.api.database).create_dashboard_session('expired', 'expired-token', -1)
        self.api.session['session_id'] = 'expired'
        url = '/api/v1/guilds/1/modules/welcome'
        self.assertEqual(self.api.client.get(url).status_code, 401)
        self.assertEqual(self.api.client.put(url, json={}, headers=self.api.headers).status_code, 401)
        self.api.discord.can_manage.assert_not_awaited()

    def test_concurrent_rule_updates_return_one_success_and_one_conflict(self):
        from concurrent.futures import ThreadPoolExecutor
        root = '/api/v1/guilds/1/moderation/automod/rules'
        value = {**default_rule('keyword'), 'name': 'Keyword', 'trigger_config': {'keywords': ['blocked']}}
        created = self.api.client.post(root, json=value, headers=self.api.headers)
        self.assertEqual(created.status_code, 201, created.text)
        item = created.json()
        def update(name):
            return self.api.client.put(root + '/' + str(item['id']), json={**value, 'revision': item['revision'], 'name': name}, headers=self.api.headers)
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(update, ['first', 'second']))
        self.assertEqual(sorted(response.status_code for response in responses), [200, 409])
        loser = next(response for response in responses if response.status_code == 409)
        self.assertEqual(loser.json()['detail']['code'], 'revision_conflict')
