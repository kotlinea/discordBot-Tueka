import tempfile
import time
import unittest
import hashlib
import hmac
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from social_models import default_templates, normalize_account, render_template, validate_subscription
from social_providers import _entries_from_atom, _entries_from_rss
from storage import GuildStorage
from social_webhooks import verify_twitch_signature, verify_youtube_signature


class SocialModelTests(unittest.TestCase):
    def test_account_normalization_preserves_youtube_channel_id(self):
        self.assertEqual(normalize_account("youtube", "https://youtube.com/channel/UCAbC_123"), "UCAbC_123")
        self.assertEqual(normalize_account("x", "@OpenAI"), "openai")
        with self.assertRaises(ValueError):
            normalize_account("tiktok", "name;shutdown")

    def test_templates_reject_unknown_variables(self):
        with self.assertRaises(ValueError):
            validate_subscription("x", {"account": "openai", "channel_id": 1, "events": ["post"], "templates": {"post": {"title": "{secret}"}}})
        value = render_template("{account}: {title}", {"account": "Tueka", "title": "Update"}, limit=100)
        self.assertEqual(value, "Tueka: Update")

    def test_feed_parsers_return_stable_ids(self):
        atom = """<feed xmlns='http://www.w3.org/2005/Atom' xmlns:yt='http://www.youtube.com/xml/schemas/2015'><entry><yt:videoId>v1</yt:videoId><yt:channelId>UC1</yt:channelId><title>Title</title><link href='https://youtu.be/v1'/><author><name>Creator</name></author></entry></feed>"""
        rss = "<rss><channel><item><guid>p1</guid><title>Post</title><link>https://instagram.com/p/1</link></item></channel></rss>"
        self.assertEqual(_entries_from_atom(atom)[0]["id"], "v1")
        self.assertEqual(_entries_from_rss(rss)[0]["id"], "p1")

    def test_webhook_signatures_and_replay_window(self):
        body, secret = b'{"event":{}}', "test-secret-value"
        youtube = "sha1=" + hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()
        self.assertTrue(verify_youtube_signature(body, youtube, secret))
        self.assertFalse(verify_youtube_signature(body + b"x", youtube, secret))
        now = datetime.now(timezone.utc)
        timestamp = now.isoformat().replace("+00:00", "Z")
        message_id = "message-1"
        twitch = "sha256=" + hmac.new(secret.encode(), (message_id + timestamp).encode() + body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_twitch_signature(body, message_id, timestamp, twitch, secret, now=now))
        self.assertFalse(verify_twitch_signature(body, message_id, timestamp, twitch, secret, now=now + timedelta(minutes=11)))


class SocialStorageV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.storage = GuildStorage(Path(self.temp.name) / "test.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def test_target_is_shared_and_claimed_once(self):
        templates = default_templates("youtube", ["video"])
        first = self.storage.save_social_subscription_v2(1, "youtube", "UCShared", 10, ["video"], {}, templates)
        second = self.storage.save_social_subscription_v2(2, "youtube", "UCShared", 20, ["video"], {}, templates)
        self.assertEqual(first["target_id"], second["target_id"])
        claimed = self.storage.claim_social_targets("worker-a")
        self.assertEqual([item["id"] for item in claimed], [first["target_id"]])
        self.assertEqual(self.storage.claim_social_targets("worker-b"), [])

    def test_initial_cursor_and_event_deduplication(self):
        templates = default_templates("x", ["post"])
        saved = self.storage.save_social_subscription_v2(1, "x", "openai", 10, ["post"], {}, templates)
        target = self.storage.claim_social_targets("worker")[0]
        self.assertTrue(self.storage.complete_social_target(target["id"], "worker", status="active", cursor={"since_id": "1"}, next_check_at=int(time.time()) + 60, external_id="42"))
        self.assertTrue(self.storage.enqueue_social_event_v2("x", "2", "42", "post", {"event": "post"}))
        self.assertFalse(self.storage.enqueue_social_event_v2("x", "2", "42", "post", {"event": "post"}))
        self.assertEqual(self.storage.social_subscription(saved["id"])["status"], "active")

    def test_revision_and_limit_are_enforced(self):
        templates = default_templates("instagram", ["post"])
        saved = self.storage.save_social_subscription_v2(1, "instagram", "one", 10, ["post"], {}, templates, max_count=1)
        with self.assertRaises(OverflowError):
            self.storage.save_social_subscription_v2(1, "instagram", "two", 10, ["post"], {}, templates, max_count=1)
        with self.assertRaises(RuntimeError):
            self.storage.save_social_subscription_v2(1, "instagram", "one", 10, ["post"], {}, templates, subscription_id=saved["id"], expected_revision=99)

    def test_last_subscription_schedules_provider_cleanup(self):
        templates = default_templates("youtube", ["video"])
        saved = self.storage.save_social_subscription_v2(1, "youtube", "UCCleanup", 10, ["video"], {}, templates)
        self.storage.delete_social_subscription(1, saved["id"])
        claimed = self.storage.claim_social_targets("cleanup-worker")
        self.assertEqual(claimed[0]["status"], "orphaned")
        self.assertTrue(self.storage.delete_social_target(claimed[0]["id"], "cleanup-worker"))

    def test_legacy_subscription_migration_is_idempotent(self):
        path = Path(self.temp.name) / "legacy.sqlite3"
        connection = sqlite3.connect(path)
        try:
            connection.execute("""CREATE TABLE social_subscriptions (id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, provider TEXT NOT NULL, account_id TEXT NOT NULL, account_name TEXT NOT NULL, channel_id INTEGER NOT NULL, role_id INTEGER, template TEXT NOT NULL DEFAULT '', events_json TEXT NOT NULL DEFAULT '[]', enabled INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, UNIQUE(guild_id,provider,account_id))""")
            connection.execute("INSERT INTO social_subscriptions VALUES(1,1,'twitch','Creator','Creator',10,NULL,'{account}','[\"live\"]',1,1,1)")
            connection.commit()
        finally:
            connection.close()
        migrated = GuildStorage(path)
        item = migrated.social_subscription(1)
        self.assertEqual(item["events"], ["live_start", "live_end"])
        self.assertTrue(item["target_id"])
        self.assertIn("live_start", item["templates"])
        GuildStorage(path)
        self.assertEqual(len(migrated.social_targets("twitch")), 1)


if __name__ == "__main__":
    unittest.main()
