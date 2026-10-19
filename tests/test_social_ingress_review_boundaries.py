"""Signed provider hints are reconciled against canonical polling state."""
import asyncio
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from db_support import prepare_database
from database import connect
from database.migrations import MIGRATIONS, apply
from database.testing import temporary_database
from guild_settings import GuildSettingsRepository
from social import SocialRepository
from social.models import default_templates
from social.providers.twitch import TwitchAdapter
from social.providers.contracts import PollResult
from social.service import SocialDeliveryService
from social.worker import SocialWorker


class SocialIngressBoundaryTests(unittest.TestCase):
    def setUp(self):
        database = prepare_database('social-ingress-' + str(id(self)), self.addCleanup)
        self.repository = SocialRepository(database)
        env = dict(DISCORD_TOKEN='offline', DISCORD_CLIENT_ID='1', DISCORD_CLIENT_SECRET='offline',
                   DISCORD_REDIRECT_URI='http://testserver/oauth/callback', SESSION_SECRET='offline',
                   DATABASE_URL=database, DASHBOARD_HTTPS_ONLY='false', SOCIAL_WEBHOOK_SECRET='synthetic-secret',
                   SOCIAL_TOKEN_ENCRYPTION_KEY='')
        with patch.dict(os.environ, env):
            spec = importlib.util.spec_from_file_location('social_ingress_boundary_app', 'dashboard/app.py')
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
        self.client = TestClient(self.module.app, follow_redirects=False)
        self.addCleanup(self.client.close)
        self.worker = object.__new__(SocialWorker)
        self.worker.repository = self.repository
        self.worker.settings = SimpleNamespace(social_poll_interval_seconds=120)
        self.worker.failures = {}

    def signed(self, event_type, message_id='synthetic-message', age=0):
        event = {'broadcaster_user_id': '42', 'broadcaster_user_login': 'creator'}
        if event_type == 'stream.online':
            event.update(id='stream-A', started_at='2026-10-19T00:00:00Z')
        body = json.dumps({'subscription': {'type': event_type}, 'event': event}).encode()
        timestamp = (datetime.now(timezone.utc) - timedelta(seconds=age)).isoformat()
        signature = 'sha256=' + hmac.new(b'synthetic-secret', (message_id + timestamp).encode() + body, hashlib.sha256).hexdigest()
        return self.client.post('/webhooks/twitch', content=body, headers={
            'twitch-eventsub-message-id': message_id, 'twitch-eventsub-message-timestamp': timestamp,
            'twitch-eventsub-message-signature': signature, 'twitch-eventsub-message-type': 'notification'})

    def target(self, cursor):
        subscription = self.repository.save_social_subscription_v2(1, 'twitch', 'creator', 10,
            ['live_start', 'live_end'], {}, default_templates('twitch'))
        with self.repository._connection() as c:
            c.execute('UPDATE social_targets SET external_id=%s,status=%s,cursor_json=%s,next_check_at=%s WHERE id=%s',
                ('42', 'active', json.dumps(cursor), 9999999999, subscription['target_id']))
        return subscription

    def poll(self, stream=None, status=200):
        def respond(request):
            if request.url.path.endswith('/token'):
                return httpx.Response(200, json={'access_token': 'synthetic'})
            if request.url.path.endswith('/users'):
                return httpx.Response(200, json={'data': [{'id': '42', 'login': 'creator', 'display_name': 'Creator'}]})
            return httpx.Response(status, json={'data': [stream] if stream else []})
        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                adapter = TwitchAdapter(SimpleNamespace(twitch_client_id='synthetic', twitch_client_secret='synthetic',
                    dashboard_base_url='', social_webhook_secret=''), client)
                targets = self.repository.claim_social_targets('synthetic-worker')
                self.assertEqual(len(targets), 1)
                await self.worker._process_target(targets[0], {'twitch': adapter})
        asyncio.run(run())

    def test_offline_retry_and_poll_end_edit_only_once(self):
        subscription = self.target({'live': True, 'stream_id': 'stream-A'})
        self.repository.set_social_live_message(subscription['id'], 'twitch', '42', 10, 20)
        settings = GuildSettingsRepository(self.repository.database_url)
        settings.set_module(1, 'twitch_updates', enabled=True)
        for _ in range(2):
            self.assertEqual(self.signed('stream.offline').status_code, 200)
        self.assertEqual(self.repository.pending_social_events(), [])
        self.assertEqual(self.repository.social_target(subscription['target_id'])['next_check_at'], 0)
        self.poll()
        self.assertEqual([e['event_key'] for e in self.repository.pending_social_events()], ['twitch:live_end:stream-A'])

        self.signed('stream.offline')
        self.poll()
        events = self.repository.pending_social_events()
        self.assertEqual(len(events), 1)
        port = SimpleNamespace(available=lambda *a: True, edit=AsyncMock(), send=AsyncMock(return_value=21))
        self.assertTrue(asyncio.run(SocialDeliveryService(self.repository, settings, port).deliver(events[0])))
        port.edit.assert_awaited_once()
        port.send.assert_not_awaited()

    def test_old_offline_and_online_hints_cannot_end_current_stream(self):
        subscription = self.target({'live': True, 'stream_id': 'stream-B'})
        self.repository.set_social_live_message(subscription['id'], 'twitch', '42', 10, 30)
        self.assertEqual(self.signed('stream.offline', 'old-A-offline', age=60).status_code, 200)
        self.assertEqual(self.signed('stream.online', 'old-A-online', age=50).status_code, 200)
        self.poll({'id': 'stream-B'})
        self.assertEqual(self.repository.pending_social_events(), [])
        self.assertEqual(self.repository.social_live_message(subscription['id'], 'twitch', '42')['discord_message_id'], 30)
        self.assertEqual(self.repository.social_target(subscription['target_id'])['cursor']['stream_id'], 'stream-B')

    def test_provider_failure_keeps_cursor_and_reconciles_after_retry(self):
        subscription = self.target({'live': True, 'stream_id': 'stream-A'})
        self.signed('stream.offline')
        self.poll(status=503)
        actual = self.repository.social_target(subscription['target_id'])
        self.assertEqual(actual['cursor'], {'live': True, 'stream_id': 'stream-A'})
        self.assertGreater(actual['next_check_at'], int(time.time()))
        self.assertEqual(self.repository.pending_social_events(), [])
        with self.repository._connection() as c:
            c.execute('UPDATE social_targets SET next_check_at=0 WHERE id=%s', (subscription['target_id'],))
        self.poll()
        self.assertEqual([e['event_key'] for e in self.repository.pending_social_events()], ['twitch:live_end:stream-A'])

    def test_online_hint_initializes_cursor_before_later_end(self):
        subscription = self.target({})
        self.signed('stream.online')
        self.assertEqual(self.repository.pending_social_events(), [])
        self.poll({'id': 'stream-A'})
        self.assertEqual(self.repository.pending_social_events(), [])
        self.assertTrue(self.repository.social_target(subscription['target_id'])['cursor']['live'])
        self.signed('stream.offline', 'later-offline')
        self.poll()
        self.assertEqual([e['event_key'] for e in self.repository.pending_social_events()], ['twitch:live_end:stream-A'])

    def test_unsigned_youtube_denial_preserves_shared_target(self):
        target = self.repository.ensure_social_target('youtube', 'UCsynthetic')
        with self.repository._connection() as c:
            c.execute('UPDATE social_targets SET status=%s,cursor_json=%s,next_check_at=%s WHERE id=%s',
                ('active', json.dumps({'seen': ['v1'], 'websub_renew_at': 9999999999}), 9999999999, target['id']))
        before = self.repository.social_target(target['id'])
        response = self.client.get('/webhooks/youtube', params={'hub.mode': 'denied',
            'hub.topic': 'https://www.youtube.com/xml/feeds/videos.xml?channel_id=UCsynthetic', 'hub.reason': 'forged-denial'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.repository.social_target(target['id']), before)
        challenge = self.client.get('/webhooks/youtube', params={'hub.mode': 'subscribe', 'hub.challenge': 'synthetic'})
        self.assertEqual(challenge.text, 'synthetic')

    def test_stale_or_missing_signature_cannot_wake_or_enqueue(self):
        subscription = self.target({'live': True, 'stream_id': 'stream-A'})
        self.assertEqual(self.signed('stream.offline', age=601).status_code, 401)
        self.assertEqual(self.client.post('/webhooks/twitch', content=b'{}').status_code, 401)
        self.assertEqual(self.repository.pending_social_events(), [])
        self.assertEqual(self.repository.social_target(subscription['target_id'])['next_check_at'], 9999999999)

    def test_hint_during_poll_keeps_immediate_confirmation_pending(self):
        subscription = self.target({'live': True, 'stream_id': 'stream-A'})
        self.signed('stream.online')
        targets = self.repository.claim_social_targets('synthetic-worker')
        self.assertEqual(len(targets), 1)
        claimed = targets[0]
        async def already_in_flight(target, *, initialize):
            # The HTTP result describes the instant before the signed offline hint.
            self.assertEqual(self.signed('stream.offline', 'during-poll').status_code, 200)
            return PollResult({'live': True, 'stream_id': 'stream-A'}, external_id='42', interval_seconds=300)
        adapter = SimpleNamespace(poll=already_in_flight)
        asyncio.run(self.worker._process_target(claimed, {'twitch': adapter}))
        actual = self.repository.social_target(subscription['target_id'])
        self.assertIsNone(actual['lease_owner'])
        self.assertEqual(actual['next_check_at'], 0)
        self.assertEqual(self.repository.pending_social_events(), [])
        self.poll()
        self.assertEqual([e['event_key'] for e in self.repository.pending_social_events()], ['twitch:live_end:stream-A'])


class SocialWakeMigrationTests(unittest.TestCase):
    def test_wake_revision_upgrade_preserves_existing_target_and_reapplies(self):
        migration = '0008_social_target_wake_revision.sql'
        with temporary_database(migrate=False) as url, tempfile.TemporaryDirectory() as directory:
            previous = Path(directory)
            for path in MIGRATIONS.glob('*.sql'):
                if path.name < migration:
                    (previous / path.name).write_text(path.read_text(encoding='utf-8'), encoding='utf-8')
            apply(url, previous)
            with connect(url) as c:
                c.execute('''INSERT INTO social_targets(provider,account_key,status,next_check_at,cursor_json,created_at,updated_at)
                    VALUES('twitch','creator','active',123,'{"live": true, "stream_id": "A"}',1,1)''')
            self.assertEqual(apply(url)['applied'], sorted(path.name for path in MIGRATIONS.glob('*.sql') if path.name >= migration))
            with connect(url) as c:
                row = c.execute('SELECT account_key,status,next_check_at,cursor_json,wake_revision FROM social_targets').fetchone()
            self.assertEqual((row['account_key'], row['status'], row['next_check_at'], row['wake_revision']),
                ('creator', 'active', 123, 0))
            self.assertEqual(json.loads(row['cursor_json']), {'live': True, 'stream_id': 'A'})
            self.assertEqual(apply(url)['applied'], [])
