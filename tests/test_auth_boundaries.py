"""Browser-bound OAuth, current write authority, and assignable role boundaries."""
import dataclasses
import time
import unittest
from contextlib import contextmanager, ExitStack
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from base64 import b64decode
from urllib.parse import parse_qs, urlparse
from unittest.mock import AsyncMock, Mock, patch
import json
import secrets

import httpx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner

import test_dashboard_routes as route_fixture
from dashboard.discord_api import DiscordAPI, PERMISSION_BITS
from social.crypto import SocialTokenCipher
from social.repository import SocialRepository
from database import connect, transaction
from database.connections import pool as database_pool
from dashboard.repository import DashboardRepository


class OAuthBoundaryTests(unittest.TestCase):
    setUp = route_fixture.DashboardRouteTests.setUp
    login = route_fixture.DashboardRouteTests.login

    def login_state(self, client=None):
        response = (client or self.client).get('/login')
        self.assertEqual(response.status_code, 303)
        return parse_qs(urlparse(response.headers['location']).query)['state'][0]

    def callback(self, state, client=None):
        return (client or self.client).get('/oauth/callback', params={'state': state, 'code': 'offline-code'})

    def configure_social(self):
        self.module.settings = dataclasses.replace(self.module.settings,
            tiktok_client_key='offline-key', tiktok_client_secret='offline-secret',
            tiktok_redirect_uri='http://testserver/social/oauth/tiktok/callback',
            instagram_app_id='offline-id', instagram_app_secret='offline-secret',
            instagram_redirect_uri='http://testserver/social/oauth/instagram/callback')
        self.module.social_cipher = SocialTokenCipher(Fernet.generate_key().decode())
        self.module.api.can_manage.return_value = True

    def begin_social(self, provider='tiktok'):
        csrf = self.client.get('/api/v1/session').json()['csrf_token']
        response = self.client.post(f'/social/oauth/{provider}/connect/1', data={'csrf_token': csrf})
        self.assertEqual(response.status_code, 303)
        return parse_qs(urlparse(response.headers['location']).query)['state'][0]

    def finish_social(self, state, provider='tiktok', client=None):
        return (client or self.client).get(f'/social/oauth/{provider}/callback',
            params={'state': state, 'code': 'offline-code'})

    def provider(self, *, error=None, side_effect=None):
        fake = Mock()
        fake.post = AsyncMock(side_effect=side_effect or error, return_value=httpx.Response(200,
            json={'access_token': 'offline-provider-token', 'open_id': 'offline-account', 'user_id': 'offline-account'},
            request=httpx.Request('POST', 'https://provider.example.test/token')))
        context = AsyncMock()
        context.__aenter__.return_value = fake
        return fake, patch.object(self.module.httpx, 'AsyncClient', return_value=context)

    def restore_cookie(self, cookie):
        self.client.cookies.set('session', cookie, domain='testserver.local', path='/')

    def test_login_state_requires_initiating_browser_and_remains_single_use(self):
        state = self.login_state()
        self.assertEqual(self.callback('無効なstate').status_code, 400)
        other = TestClient(self.module.app, follow_redirects=False)
        self.addCleanup(other.close)
        self.assertEqual(self.callback(state, other).status_code, 400)
        self.assertEqual(other.get('/api/v1/session').status_code, 401)
        self.module.api.exchange_code.assert_not_awaited()
        self.assertEqual(self.callback(state).status_code, 303)
        self.assertEqual(self.client.get('/api/v1/session').status_code, 200)
        self.assertEqual(self.callback(state).status_code, 400)
        self.assertEqual(self.module.api.exchange_code.await_count, 1)

    def test_login_restart_rejects_previous_state(self):
        first = self.login_state()
        old_cookie = self.client.cookies.get('session')
        second = self.login_state()
        current_cookie = self.client.cookies.get('session')
        self.restore_cookie(old_cookie)
        self.assertEqual(self.callback(first).status_code, 400)
        self.restore_cookie(current_cookie)
        self.assertEqual(self.callback(second).status_code, 303)

    def test_logout_invalidates_pending_login_even_if_old_cookie_is_restored(self):
        state = self.login_state()
        cookie = self.client.cookies.get('session')
        self.client.get('/logout')
        self.restore_cookie(cookie)
        self.assertEqual(self.callback(state).status_code, 400)
        self.module.api.exchange_code.assert_not_awaited()

    def test_expired_login_state_never_exchanges_code(self):
        state = self.login_state()
        with patch('dashboard.repository.time.time', return_value=time.time() + 601):
            self.assertEqual(self.callback(state).status_code, 400)
        self.module.api.exchange_code.assert_not_awaited()

    def test_failed_discord_exchange_consumes_state_without_creating_session(self):
        state = self.login_state()
        self.module.api.exchange_code.side_effect = httpx.ReadTimeout('offline failure')
        self.assertEqual(self.callback(state).status_code, 401)
        self.assertEqual(self.callback(state).status_code, 400)
        self.assertEqual(self.client.get('/api/v1/session').status_code, 401)
        with self.module.dashboard_repository._connection() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) AS total FROM oauth_states').fetchone()['total'], 0)

    def test_cancelled_discord_exchange_cleans_up_claim(self):
        import asyncio
        from fastapi import Request

        state = self.login_state()
        self.module.api.exchange_code.side_effect = asyncio.CancelledError()
        request = Request({'type': 'http', 'session': {'oauth_state': state}})
        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(self.module.oauth_callback(request, code='offline-code', state=state))
        with self.module.dashboard_repository._connection() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) AS total FROM oauth_states').fetchone()['total'], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) AS total FROM dashboard_sessions').fetchone()['total'], 0)

    def test_failed_login_completion_cleans_up_claim(self):
        state = self.login_state()
        with patch.object(self.module.dashboard_repository, 'complete_oauth_exchange', side_effect=RuntimeError('offline completion failure')):
            with self.assertRaisesRegex(RuntimeError, 'offline completion failure'):
                self.callback(state)
        with self.module.dashboard_repository._connection() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) AS total FROM oauth_states').fetchone()['total'], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) AS total FROM dashboard_sessions').fetchone()['total'], 0)

    def test_logout_during_discord_exchange_prevents_session_revival(self):
        state = self.login_state()
        cookie = self.client.cookies.get('session')
        callback_client = TestClient(self.module.app, follow_redirects=False)
        self.addCleanup(callback_client.close)
        callback_client.cookies.set('session', cookie, domain='testserver.local', path='/')
        exchange_started, release_exchange = Event(), Event()

        async def exchange(code):
            import asyncio
            exchange_started.set()
            if not await asyncio.to_thread(release_exchange.wait, 5):
                raise AssertionError('Exchange was not released after logout')
            return {'access_token': 'offline-exchanged-token', 'expires_in': 3600}

        self.module.api.exchange_code.side_effect = exchange
        with ThreadPoolExecutor(max_workers=1) as workers:
            pending = workers.submit(self.callback, state, callback_client)
            try:
                self.assertTrue(exchange_started.wait(5), 'Discord exchange never started')
                self.assertEqual(self.client.get('/logout').status_code, 303)
                release_exchange.set()
                response = pending.result(timeout=5)
            finally:
                release_exchange.set()
        with self.module.dashboard_repository._connection() as connection:
            count = connection.execute('SELECT COUNT(*) AS total FROM dashboard_sessions').fetchone()['total']
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(callback_client.get('/api/v1/session').status_code, 401)
        self.assertEqual(count, 0)

    def test_second_callback_cannot_reuse_in_flight_discord_state(self):
        state = self.login_state()
        cookie = self.client.cookies.get('session')
        callback_client = TestClient(self.module.app, follow_redirects=False)
        self.addCleanup(callback_client.close)
        callback_client.cookies.set('session', cookie, domain='testserver.local', path='/')
        exchange_started, release_exchange = Event(), Event()

        async def exchange(code):
            import asyncio
            exchange_started.set()
            if not await asyncio.to_thread(release_exchange.wait, 5):
                raise AssertionError('First exchange was not released')
            return {'access_token': 'offline-exchanged-token', 'expires_in': 3600}

        self.module.api.exchange_code.side_effect = exchange
        with ThreadPoolExecutor(max_workers=1) as workers:
            pending = workers.submit(self.callback, state, callback_client)
            try:
                self.assertTrue(exchange_started.wait(5), 'First exchange never started')
                self.assertEqual(self.callback(state).status_code, 400)
                self.assertEqual(self.module.api.exchange_code.await_count, 1)
                release_exchange.set()
                self.assertEqual(pending.result(timeout=5).status_code, 303)
            finally:
                release_exchange.set()
        self.assertEqual(callback_client.get('/api/v1/session').status_code, 200)

    def test_new_login_can_finish_while_previous_exchange_is_cancelled(self):
        first_state = self.login_state()
        first_client = TestClient(self.module.app, follow_redirects=False)
        self.addCleanup(first_client.close)
        first_client.cookies.set('session', self.client.cookies.get('session'), domain='testserver.local', path='/')
        exchange_started, release_exchange = Event(), Event()
        calls = 0

        async def exchange(code):
            import asyncio
            nonlocal calls
            calls += 1
            if calls == 1:
                exchange_started.set()
                if not await asyncio.to_thread(release_exchange.wait, 5):
                    raise AssertionError('Previous exchange was not released')
            return {'access_token': 'offline-exchanged-token', 'expires_in': 3600}

        self.module.api.exchange_code.side_effect = exchange
        with ThreadPoolExecutor(max_workers=1) as workers:
            pending = workers.submit(self.callback, first_state, first_client)
            try:
                self.assertTrue(exchange_started.wait(5), 'Previous exchange never started')
                self.assertEqual(self.callback(self.login_state()).status_code, 303)
                release_exchange.set()
                self.assertEqual(pending.result(timeout=5).status_code, 400)
            finally:
                release_exchange.set()
        self.assertEqual(self.client.get('/api/v1/session').status_code, 200)
        self.assertEqual(first_client.get('/api/v1/session').status_code, 401)

    def test_social_provider_success_is_bound_to_browser_and_replay_is_rejected(self):
        self.configure_social()
        self.login()
        other = TestClient(self.module.app, follow_redirects=False)
        self.addCleanup(other.close)
        self.assertEqual(self.callback(self.login_state(other), other).status_code, 303)
        for provider in ('tiktok', 'instagram'):
            with self.subTest(provider=provider):
                state = self.begin_social(provider)
                self.assertEqual(self.finish_social('無効なstate', provider).status_code, 400)
                self.assertEqual(self.finish_social(state, provider, other).status_code, 400)
                wrong_provider = 'instagram' if provider == 'tiktok' else 'tiktok'
                self.assertEqual(self.finish_social(state, wrong_provider).status_code, 400)
                fake, provider_patch = self.provider()
                self.module.api.can_manage.reset_mock()
                with provider_patch:
                    self.assertEqual(self.finish_social(state, provider).status_code, 303)
                fake.post.assert_awaited_once()
                self.assertEqual(self.module.api.can_manage.await_count, 2)
                self.assertTrue(all(call.kwargs == {'use_cache': False}
                    for call in self.module.api.can_manage.await_args_list))
                rows = self.module.social_repository.social_connections(1, provider)
                self.assertEqual(len(rows), 1)
                self.assertEqual(self.module.social_cipher.decrypt(rows[0]['access_token_encrypted']), 'offline-provider-token')
                self.assertEqual(self.finish_social(state, provider).status_code, 400)

    def test_logged_out_social_callback_cannot_restore_a_revoked_session(self):
        self.configure_social()
        self.login()
        state = self.begin_social()
        cookie = self.client.cookies.get('session')
        self.client.get('/logout')
        self.restore_cookie(cookie)
        fake, provider_patch = self.provider()
        with provider_patch:
            self.assertEqual(self.finish_social(state).status_code, 401)
        fake.post.assert_not_awaited()
        self.assertIsNone(self.module.social_repository.consume_social_oauth_state(state, 'tiktok'))
        self.assertEqual(self.module.social_repository.social_connections(1), [])

    def test_new_login_invalidates_social_state_for_previous_session(self):
        self.configure_social()
        self.login()
        state = self.begin_social()
        old_cookie = self.client.cookies.get('session')
        self.assertEqual(self.callback(self.login_state()).status_code, 303)
        self.assertEqual(self.finish_social(state).status_code, 400)
        self.restore_cookie(old_cookie)
        self.assertEqual(self.finish_social(state).status_code, 400)
        self.assertEqual(self.module.social_repository.social_connections(1), [])

    def test_social_permission_loss_before_exchange_prevents_provider_call(self):
        self.configure_social()
        self.login()
        state = self.begin_social()
        self.module.api.can_manage.return_value = False
        fake, provider_patch = self.provider()
        with provider_patch:
            self.assertEqual(self.finish_social(state).status_code, 403)
        fake.post.assert_not_awaited()
        self.assertEqual(self.module.social_repository.social_connections(1), [])

    def test_expired_social_state_never_calls_provider(self):
        self.configure_social()
        self.login()
        state = self.begin_social()
        fake, provider_patch = self.provider()
        with provider_patch, patch('social.repository.time.time', return_value=time.time() + 601):
            self.assertEqual(self.finish_social(state).status_code, 400)
        fake.post.assert_not_awaited()
        self.assertEqual(self.module.social_repository.social_connections(1), [])

    def test_social_permission_loss_during_exchange_prevents_save(self):
        self.configure_social()
        self.login()
        state = self.begin_social()
        self.module.api.can_manage.side_effect = [True, False]
        fake, provider_patch = self.provider()
        with provider_patch:
            self.assertEqual(self.finish_social(state).status_code, 403)
        fake.post.assert_awaited_once()
        self.assertEqual(self.module.social_repository.social_connections(1), [])

    def test_session_revoked_during_provider_exchange_prevents_save(self):
        self.configure_social()
        self.login()
        state = self.begin_social()
        cookie = self.client.cookies.get('session')
        payload = json.loads(b64decode(TimestampSigner('test-session-secret').unsign(cookie)))

        async def revoke(*args, **kwargs):
            self.module.dashboard_repository.delete_dashboard_session(payload['session_id'])
            return httpx.Response(200, json={'access_token': 'offline-token', 'open_id': 'offline-account'},
                request=httpx.Request('POST', 'https://provider.example.test/token'))

        fake, provider_patch = self.provider(side_effect=revoke)
        with provider_patch:
            self.assertEqual(self.finish_social(state).status_code, 401)
        fake.post.assert_awaited_once()
        self.assertEqual(self.module.social_repository.social_connections(1), [])

    def test_provider_failure_saves_nothing_and_consumes_state(self):
        self.configure_social()
        self.login()
        state = self.begin_social()
        fake, provider_patch = self.provider(error=httpx.ReadTimeout('offline failure'))
        with provider_patch:
            self.assertEqual(self.finish_social(state).status_code, 502)
        self.assertEqual(self.module.social_repository.social_connections(1), [])
        self.assertEqual(self.finish_social(state).status_code, 400)

    def test_logout_during_final_authorization_prevents_social_save(self):
        self.configure_social()
        self.login()
        state = self.begin_social()
        payload = json.loads(b64decode(TimestampSigner('test-session-secret').unsign(self.client.cookies.get('session'))))
        checks = 0

        async def live_authority(*args, **kwargs):
            nonlocal checks
            checks += 1
            if checks == 2:
                self.module.dashboard_repository.delete_dashboard_session(payload['session_id'])
            return True

        self.module.api.can_manage.side_effect = live_authority
        fake, provider_patch = self.provider()
        with provider_patch:
            response = self.finish_social(state)
        self.assertEqual(checks, 2)
        fake.post.assert_awaited_once()
        self.assertIsNone(self.module.dashboard_repository.dashboard_session_token(payload['session_id']))
        self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(self.module.social_repository.social_connections(1), [])


class SessionGuardTransactionTests(unittest.TestCase):
    def setUp(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from db_support import prepare_database

        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = prepare_database(Path(temporary.name) / 'session-guard.db', self.addCleanup)
        self.repository = DashboardRepository(self.database)
        self.social = SocialRepository(self.database)
        self.repository.create_dashboard_session('guarded-session', 'expected-token', 3600)

    def save(self, connection):
        self.social.save_social_connection(1, 'tiktok', 'offline-account', 'Offline account',
            'encrypted-offline-token', None, None, _conn=connection)

    def guarded_save(self):
        with self.repository.guard_dashboard_session('guarded-session', 'expected-token') as connection:
            self.save(connection)

    def wait_until(self, predicate, message):
        deadline = time.monotonic() + 5
        tick = Event()
        while time.monotonic() < deadline:
            if predicate():
                return
            tick.wait(0.01)
        self.fail(message)

    def wait_for_blocker(self, waiting_pid, blocking_pid):
        with connect(self.database, read_only=True, autocommit=True) as observer:
            self.wait_until(lambda: observer.execute('SELECT %s = ANY(pg_blocking_pids(%s)) AS blocked',
                (blocking_pid, waiting_pid)).fetchone()['blocked'], 'Expected the session row lock to block the competing operation')

    def test_guard_rejects_a_different_expected_token(self):
        with self.assertRaises(PermissionError):
            with self.repository.guard_dashboard_session('guarded-session', 'different-token') as connection:
                self.save(connection)
        self.assertEqual(self.social.social_connections(1), [])

    def test_guard_and_social_save_rollback_together(self):
        with self.assertRaisesRegex(RuntimeError, 'rollback probe'):
            with self.repository.guard_dashboard_session('guarded-session', 'expected-token') as connection:
                self.save(connection)
                raise RuntimeError('rollback probe')
        self.assertEqual(self.social.social_connections(1), [])
        self.assertEqual(self.repository.dashboard_session_token('guarded-session'), 'expected-token')

    def test_logout_committed_while_guard_waits_for_row_lock_prevents_save(self):
        entered, pids = Event(), []

        @contextmanager
        def observed_connection():
            with transaction(self.database) as connection:
                pids.append(connection.info.backend_pid)
                entered.set()
                yield connection

        with connect(self.database) as logout:
            logout.execute('DELETE FROM dashboard_sessions WHERE session_id=%s', ('guarded-session',))
            with ThreadPoolExecutor(max_workers=1) as workers, patch.object(self.repository, '_connection', observed_connection):
                pending = workers.submit(self.guarded_save)
                try:
                    self.assertTrue(entered.wait(5), 'Guard never requested a connection')
                    self.wait_for_blocker(pids[0], logout.info.backend_pid)
                    logout.commit()
                    with self.assertRaises(PermissionError):
                        pending.result(timeout=5)
                finally:
                    logout.rollback()
        self.assertEqual(self.social.social_connections(1), [])
        self.assertIsNone(self.repository.dashboard_session_token('guarded-session'))

    def assert_pool_wait_rechecks_session(self, *, expire=False):
        entered = Event()
        holders = ExitStack()
        current_pool = database_pool(self.database)

        @contextmanager
        def observed_connection():
            entered.set()
            with transaction(self.database) as connection:
                yield connection

        with patch('dashboard.repository.time.time', return_value=time.time()) as clock:
            for _ in range(4):
                holders.enter_context(current_pool.connection())
            with ThreadPoolExecutor(max_workers=1) as workers, patch.object(self.repository, '_connection', observed_connection):
                pending = workers.submit(self.guarded_save)
                try:
                    self.assertTrue(entered.wait(5), 'Guard never requested the exhausted pool')
                    self.wait_until(lambda: current_pool.get_stats()['requests_waiting'] > 0,
                        'Guard never queued for the exhausted pool')
                    if expire:
                        clock.return_value += 3601
                    else:
                        with connect(self.database) as logout:
                            logout.execute('DELETE FROM dashboard_sessions WHERE session_id=%s', ('guarded-session',))
                    holders.close()
                    with self.assertRaises(PermissionError):
                        pending.result(timeout=5)
                finally:
                    holders.close()
        self.assertEqual(self.social.social_connections(1), [])

    def test_logout_committed_while_guard_waits_for_pool_prevents_save(self):
        self.assert_pool_wait_rechecks_session()

    def test_expiry_while_guard_waits_for_pool_prevents_save(self):
        self.assert_pool_wait_rechecks_session(expire=True)

    def test_save_holding_session_lock_commits_before_logout(self):
        save_ready, release_save, delete_started = Event(), Event(), Event()
        delete_pids = []
        logout_repository = DashboardRepository(self.database)

        def save_first():
            with self.repository.guard_dashboard_session('guarded-session', 'expected-token') as connection:
                self.save(connection)
                save_ready.set()
                if not release_save.wait(5):
                    raise AssertionError('Save transaction was not released')

        @contextmanager
        def observed_delete_connection():
            with transaction(self.database) as connection:
                delete_pids.append(connection.info.backend_pid)
                delete_started.set()
                yield connection

        save_pids = []

        @contextmanager
        def observed_save_connection():
            with transaction(self.database) as connection:
                save_pids.append(connection.info.backend_pid)
                yield connection

        with ThreadPoolExecutor(max_workers=2) as workers, \
                patch.object(self.repository, '_connection', observed_save_connection), \
                patch.object(logout_repository, '_connection', observed_delete_connection):
            saving = workers.submit(save_first)
            try:
                self.assertTrue(save_ready.wait(5), 'Save never acquired its session row lock')
                deleting = workers.submit(logout_repository.delete_dashboard_session, 'guarded-session')
                self.assertTrue(delete_started.wait(5), 'Logout never requested its row lock')
                self.wait_for_blocker(delete_pids[0], save_pids[0])
                self.assertEqual(self.social.social_connections(1), [])
                release_save.set()
                saving.result(timeout=5)
                deleting.result(timeout=5)
            finally:
                release_save.set()
        self.assertEqual(len(self.social.social_connections(1)), 1)
        self.assertIsNone(self.repository.dashboard_session_token('guarded-session'))


class OAuthFlowTransactionTests(unittest.TestCase):
    setUp = SessionGuardTransactionTests.setUp
    wait_until = SessionGuardTransactionTests.wait_until
    wait_for_blocker = SessionGuardTransactionTests.wait_for_blocker

    def claim(self):
        state = secrets.token_urlsafe(32)
        self.repository.create_oauth_state(state)
        self.assertTrue(self.repository.begin_oauth_exchange(state))
        return state

    def complete(self, state):
        return self.repository.complete_oauth_exchange(state, 'login-session', 'offline-login-token', 3600)

    def test_inflight_namespace_is_never_accepted_as_a_browser_nonce(self):
        state = self.claim()
        internal = 'discord-exchange:' + state
        self.assertFalse(self.repository.begin_oauth_exchange(internal))
        self.assertFalse(self.repository.cancel_oauth_state(internal))
        self.assertFalse(self.complete(internal))
        self.assertFalse(self.repository.consume_oauth_state(internal))
        with self.assertRaises(ValueError):
            self.repository.create_oauth_state(internal)
        self.assertFalse(self.repository.begin_oauth_exchange(state))
        self.assertTrue(self.complete(state))
        self.assertFalse(self.complete(state))

    def test_expired_inflight_claim_is_cleaned_with_expired_pending_states(self):
        with patch('dashboard.repository.time.time', return_value=1000) as clock:
            state = self.claim()
            clock.return_value = 1601
            fresh = secrets.token_urlsafe(32)
            self.repository.create_oauth_state(fresh)
            self.assertFalse(self.complete(state))
            with self.repository._connection() as connection:
                states = connection.execute('SELECT state FROM oauth_states').fetchall()
        self.assertEqual([row['state'] for row in states], [fresh])

    def test_session_insert_failure_rolls_back_claim_consumption(self):
        state = self.claim()
        with patch.object(self.repository, 'create_dashboard_session', side_effect=RuntimeError('offline insert failure')):
            with self.assertRaisesRegex(RuntimeError, 'offline insert failure'):
                self.complete(state)
        self.assertTrue(self.repository.cancel_oauth_state(state))
        self.assertFalse(self.complete(state))
        self.assertIsNone(self.repository.dashboard_session_token('login-session'))

    def test_logout_committed_before_completion_row_lock_prevents_session(self):
        state = self.claim()
        entered, pids = Event(), []

        @contextmanager
        def observed_connection():
            with transaction(self.database) as connection:
                pids.append(connection.info.backend_pid)
                entered.set()
                yield connection

        with connect(self.database) as logout:
            logout.execute('DELETE FROM oauth_states')
            with ThreadPoolExecutor(max_workers=1) as workers, patch.object(self.repository, '_connection', observed_connection):
                pending = workers.submit(self.complete, state)
                try:
                    self.assertTrue(entered.wait(5), 'Completion never acquired its connection')
                    self.wait_for_blocker(pids[0], logout.info.backend_pid)
                    logout.commit()
                    self.assertFalse(pending.result(timeout=5))
                finally:
                    logout.rollback()
        self.assertIsNone(self.repository.dashboard_session_token('login-session'))

    def test_expiry_during_completion_row_lock_wait_prevents_session(self):
        state = self.claim()
        entered, pids = Event(), []

        @contextmanager
        def observed_connection():
            with transaction(self.database) as connection:
                pids.append(connection.info.backend_pid)
                entered.set()
                yield connection

        with patch('dashboard.repository.time.time', return_value=time.time()) as clock, connect(self.database) as blocker:
            blocker.execute('SELECT state FROM oauth_states FOR UPDATE')
            with ThreadPoolExecutor(max_workers=1) as workers, patch.object(self.repository, '_connection', observed_connection):
                pending = workers.submit(self.complete, state)
                try:
                    self.assertTrue(entered.wait(5), 'Completion never acquired its connection')
                    self.wait_for_blocker(pids[0], blocker.info.backend_pid)
                    clock.return_value += 601
                    blocker.commit()
                    self.assertFalse(pending.result(timeout=5))
                finally:
                    blocker.rollback()
        self.assertIsNone(self.repository.dashboard_session_token('login-session'))

    def test_completion_holding_flow_lock_creates_session_before_cancellation(self):
        state = self.claim()
        inserted, release, cancelling = Event(), Event(), Event()
        completion_pids, cancel_pids = [], []
        cancellation_repository = DashboardRepository(self.database)
        create_session = self.repository.create_dashboard_session

        def insert_then_wait(*args, **kwargs):
            create_session(*args, **kwargs)
            inserted.set()
            if not release.wait(5):
                raise AssertionError('Completion was not released')

        @contextmanager
        def completion_connection():
            with transaction(self.database) as connection:
                completion_pids.append(connection.info.backend_pid)
                yield connection

        @contextmanager
        def cancellation_connection():
            with transaction(self.database) as connection:
                cancel_pids.append(connection.info.backend_pid)
                cancelling.set()
                yield connection

        with ThreadPoolExecutor(max_workers=2) as workers, \
                patch.object(self.repository, 'create_dashboard_session', side_effect=insert_then_wait), \
                patch.object(self.repository, '_connection', completion_connection), \
                patch.object(cancellation_repository, '_connection', cancellation_connection):
            completing = workers.submit(self.complete, state)
            try:
                self.assertTrue(inserted.wait(5), 'Completion never inserted its uncommitted session')
                cancellation = workers.submit(cancellation_repository.cancel_oauth_state, state)
                self.assertTrue(cancelling.wait(5), 'Cancellation never requested its connection')
                self.wait_for_blocker(cancel_pids[0], completion_pids[0])
                release.set()
                self.assertTrue(completing.result(timeout=5))
                self.assertFalse(cancellation.result(timeout=5))
            finally:
                release.set()
        self.assertEqual(self.repository.dashboard_session_token('login-session'), 'offline-login-token')


class AssignableRoleBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_channel_roles_remain_selectable_but_management_roles_do_not(self):
        normal_permissions = sum(PERMISSION_BITS[name] for name in (
            'view_channel', 'send_messages', 'add_reactions', 'read_message_history', 'embed_links', 'attach_files'))
        roles = [
            {'id': '1', 'name': '@everyone', 'permissions': '0', 'position': 0},
            {'id': '2', 'name': 'Bot', 'permissions': '8', 'position': 10},
            {'id': '3', 'name': 'Member', 'permissions': str(normal_permissions), 'position': 1},
            {'id': '4', 'name': 'Empty member', 'permissions': '0', 'position': 2},
            {'id': '5', 'name': 'Managed member', 'permissions': '0', 'position': 2, 'managed': True},
            {'id': '6', 'name': 'Peer role', 'permissions': '0', 'position': 10},
            {'id': '7', 'name': 'Higher role', 'permissions': '0', 'position': 11},
        ]
        for index, name in enumerate(('manage_roles', 'kick_members', 'ban_members', 'moderate_members',
                'manage_channels', 'manage_messages', 'manage_threads', 'move_members', 'view_audit_log'), 20):
            roles.append({'id': str(index), 'name': name, 'permissions': str(PERMISSION_BITS[name]), 'position': 3})

        def transport(request):
            if request.url.path.endswith('/channels'):
                payload = []
            elif request.url.path.endswith('/roles'):
                payload = roles
            elif request.url.path.endswith('/members/2'):
                payload = {'roles': ['2']}
            else:
                raise AssertionError(str(request.url))
            return httpx.Response(200, json=payload)

        api = DiscordAPI('offline', '2', 'offline', 'http://testserver/callback')
        api._client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        self.addAsyncCleanup(api.close)
        _, selected, _ = await api.guild_resources(1, use_cache=False)
        self.assertEqual([role['id'] for role in selected], ['3', '4'])
