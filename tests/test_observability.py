"""Real database pressure/failure and secret-free operational observations."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
import logging
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import connect, transaction
from database.connections import pool, pool_statistics
from database.testing import temporary_database
from jobs import Outcome
from observability.export import render
from observability.heartbeat import ServiceHeartbeat, local_ready
from observability.http import router, observe_request
from observability.logging import SafeJsonFormatter
from observability.metrics import Registry, registry
from observability.repository import heartbeat, snapshot
from suggestions import SuggestionRepository


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        context = temporary_database()
        self.url = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'index.html').write_text('assets')
        self.token = 'monitor-test-' + 'a' * 40
        app = FastAPI()
        app.include_router(router(self.url, (self.root,), self.token))
        app.middleware('http')(observe_request)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_health_requires_assets_and_current_schema_but_liveness_does_not(self):
        self.assertEqual(self.client.get('/health/ready').status_code, 200)
        (self.root / 'index.html').unlink()
        self.assertEqual(self.client.get('/health/ready').status_code, 503)
        (self.root / 'index.html').write_text('assets')
        with transaction(self.url) as client:
            client.execute("UPDATE schema_migrations SET checksum='wrong' WHERE version=1")
        self.assertEqual(self.client.get('/health/ready').status_code, 503)
        self.assertEqual(self.client.get('/health/live').status_code, 200)

    def test_authenticated_metrics_never_contain_payloads_or_credentials(self):
        self.assertEqual(self.client.get('/internal/metrics').status_code, 404)
        self.assertEqual(self.client.get('/internal/metrics', headers={'Authorization': 'Bearer bad'}).status_code, 404)
        SuggestionRepository(self.url).create(1, 2, 3, {'idea': 'PRIVATE_BODY'})
        response = self.client.get('/internal/metrics?code=PRIVATE_QUERY', headers={'Authorization': 'Bearer ' + self.token})
        heartbeat(self.url, 'dashboard', 'metrics-test', True, registry.snapshot())
        response = self.client.get('/internal/metrics', headers={'Authorization': 'Bearer ' + self.token})
        self.assertEqual(response.status_code, 200)
        self.assertIn('tueka_queue_active', response.text)
        for private in ('PRIVATE_BODY', 'PRIVATE_QUERY', self.token, self.url):
            self.assertNotIn(private, response.text)

    def test_expired_and_stopped_heartbeats_are_detected(self):
        for service in ('bot', 'dashboard', 'social-worker'):
            heartbeat(self.url, service, service, True, [])
        self.assertEqual(snapshot(self.url)['alerts'], [])
        with transaction(self.url) as client:
            client.execute("UPDATE runtime_heartbeats SET observed_at=observed_at-60 WHERE service='social-worker'")
        self.assertIn('service_unavailable:social-worker', snapshot(self.url)['alerts'])
        heartbeat(self.url, 'bot', 'bot', False, [])
        self.assertFalse(snapshot(self.url)['services']['bot']['ready'])
        heartbeat(self.url, 'bot', 'new-bot', True, [])
        self.assertTrue(snapshot(self.url)['services']['bot']['ready'])

    def test_delivery_delay_and_failed_attempt_are_visible_without_error_text(self):
        repository = SuggestionRepository(self.url)
        repository.settings.set_module(1, 'suggestions', enabled=True, settings={})
        repository.create(1, 2, 3, {'idea': 'PRIVATE_BODY'})
        with transaction(self.url) as client:
            client.execute('UPDATE suggestion_outbox SET created_at=%s,available_at=%s', (int(time.time())-900, int(time.time())-900))
        self.assertIn('queue_delayed:suggestion_outbox', snapshot(self.url)['alerts'])
        claim = repository.outbox_jobs.claim('monitor-test')
        self.assertTrue(repository.outbox_jobs.finish(claim, Outcome('PRIVATE_DELIVERY_ERROR')))
        values = snapshot(self.url)
        self.assertIn('dead_letter:suggestion_outbox', values['alerts'])
        self.assertNotIn('PRIVATE', render(values))
        self.assertTrue(any(item['name'] == 'job_results_total' and item['labels'] == {'outcome': 'failed', 'queue': 'suggestion_outbox'} for item in registry.snapshot()))

    def test_pool_saturation_does_not_block_liveness_and_recovers(self):
        with ExitStack() as stack, ThreadPoolExecutor(max_workers=1) as executor:
            for _ in range(4):
                stack.enter_context(pool(self.url).connection())
            pending = executor.submit(self.client.get, '/health/ready')
            time.sleep(.1)
            self.assertEqual(self.client.get('/health/live').status_code, 200)
            self.assertFalse(pending.done())
            self.assertEqual(pending.result(timeout=5).status_code, 503)
            self.assertGreater(pool_statistics()['requests_errors'], 0)
        self.assertEqual(self.client.get('/health/ready').status_code, 200)

    def test_future_work_is_not_reported_as_overdue(self):
        SuggestionRepository(self.url).create(1, 2, 3, {'idea': 'scheduled'})
        with transaction(self.url) as client:
            client.execute('UPDATE suggestion_outbox SET created_at=%s,available_at=%s', (int(time.time())-900, int(time.time())+900))
        values = snapshot(self.url)
        self.assertEqual(values['queues']['suggestion_outbox']['active'], 1)
        self.assertEqual(values['queues']['suggestion_outbox']['oldest_due_age_seconds'], 0)
        self.assertNotIn('queue_delayed:suggestion_outbox', values['alerts'])

    def test_lock_wait_and_lock_timeout_are_observed(self):
        with transaction(self.url) as client:
            client.execute('CREATE TABLE monitor_lock(id INTEGER PRIMARY KEY, value INTEGER)')
            client.execute('INSERT INTO monitor_lock VALUES(1,0)')

        def blocked():
            try:
                with transaction(self.url) as client:
                    client.execute("SET LOCAL lock_timeout='1500ms'")
                    client.execute('UPDATE monitor_lock SET value=2 WHERE id=1')
            except Exception as error:
                return getattr(error, 'sqlstate', '')

        with ThreadPoolExecutor(max_workers=1) as executor, connect(self.url) as owner:
            owner.execute('UPDATE monitor_lock SET value=1 WHERE id=1')
            pending = executor.submit(blocked)
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                result = snapshot(self.url)
                if result['database']['lock_waiters']:
                    break
                time.sleep(.02)
            self.assertIn('database_lock_wait', result['alerts'])
            self.assertEqual(pending.result(timeout=5), '55P03')
        self.assertTrue(any(item['name'] == 'db_errors_total' and item['labels'].get('category') == 'lock_timeout' for item in registry.snapshot()))

    def test_sql_failure_metrics_do_not_change_rollback_behavior(self):
        with self.assertRaises(Exception):
            with transaction(self.url) as client:
                client.execute("INSERT INTO app_metadata VALUES('monitor_failure','private')")
                client.execute('SELECT 1/0')
        with connect(self.url) as client:
            self.assertIsNone(client.execute("SELECT * FROM app_metadata WHERE key='monitor_failure'").fetchone())
        self.assertTrue(any(item['name'] == 'db_errors_total' for item in registry.snapshot()))


class HeartbeatTests(unittest.IsolatedAsyncioTestCase):
    async def test_readiness_tracks_gateway_state_and_shutdown(self):
        context = temporary_database()
        url = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        with tempfile.TemporaryDirectory() as directory, patch('observability.heartbeat.state_path', return_value=Path(directory) / 'health.json'):
            connected = False
            observer = ServiceHeartbeat('bot', url, ready=lambda: connected)
            await observer.start()
            self.assertFalse(local_ready('bot'))
            connected = True
            await observer.publish()
            self.assertTrue(local_ready('bot'))
            await observer.stop()
            self.assertFalse(local_ready('bot'))
            self.assertFalse(snapshot(url)['services']['bot']['ready'])


class SafeMetricsTests(unittest.TestCase):
    def test_http_and_cli_threshold_configuration_is_bounded(self):
        from observability.configuration import thresholds
        with patch.dict('os.environ', {'HEARTBEAT_MAX_AGE_SECONDS': '45', 'OUTBOX_MAX_AGE_SECONDS': '600'}):
            self.assertEqual(thresholds(), {'heartbeat_age': 45, 'queue_age': 600})
        with patch.dict('os.environ', {'HEARTBEAT_MAX_AGE_SECONDS': '0', 'OUTBOX_MAX_AGE_SECONDS': '999999'}):
            self.assertEqual(thresholds(), {'heartbeat_age': 5, 'queue_age': 86400})

    def test_log_messages_arguments_exception_text_and_paths_are_not_emitted(self):
        try:
            raise ValueError('PRIVATE_EXCEPTION')
        except ValueError:
            import sys
            record = logging.LogRecord('tueka', logging.ERROR, 'PRIVATE_PATH', 10, 'PRIVATE_URL?token=%s', ('PRIVATE_TOKEN',), sys.exc_info())
        result = SafeJsonFormatter('dashboard').format(record)
        self.assertNotIn('PRIVATE', result)
        self.assertEqual(json.loads(result)['exception_type'], 'ValueError')

    def test_registry_is_bounded(self):
        metrics = Registry()
        for index in range(1000):
            metrics.add('count', route=str(index))
        self.assertLessEqual(len(metrics.snapshot()), 513)
        self.assertTrue(any(item['name'] == 'metrics_dropped_series_total' for item in metrics.snapshot()))
