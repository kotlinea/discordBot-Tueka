import tempfile
import time
import unittest
import hashlib
import hmac
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock
from datetime import datetime, timedelta, timezone
from pathlib import Path

from social_models import default_templates, normalize_account, render_template, validate_subscription
from social_providers import YouTubeAdapter, _entries_from_atom, _entries_from_rss, _youtube_channel_id_from_html
from storage import GuildStorage
from social_webhooks import verify_twitch_signature, verify_youtube_signature


class _YouTubeClient:
    def __init__(self, responses):
        self.responses = list(responses)

    async def get(self, url, **kwargs):
        expected, response = self.responses.pop(0)
        assert expected in url
        if isinstance(response, Exception):
            raise response
        return response

    async def post(self, url, **kwargs):
        expected, response = self.responses.pop(0)
        assert expected in url
        if isinstance(response, Exception):
            raise response
        return response


class SocialModelTests(unittest.TestCase):
    def test_account_normalization_preserves_youtube_channel_id(self):
        channel_id = "UCUZHFZ9jIKrLroW8LcyJEQQ"
        self.assertEqual(normalize_account("youtube", f"https://youtube.com/channel/{channel_id}"), channel_id)
        self.assertEqual(normalize_account("x", "@OpenAI"), "openai")
        with self.assertRaises(ValueError):
            normalize_account("tiktok", "name;shutdown")

    def test_youtube_account_normalization_supports_unicode_and_all_channel_urls(self):
        self.assertEqual(normalize_account("youtube", "@日本語チャンネル"), "日本語チャンネル")
        self.assertEqual(normalize_account("youtube", "https://www.youtube.com/@日本語チャンネル"), "日本語チャンネル")
        self.assertEqual(normalize_account("youtube", "https://www.youtube.com/c/日本語チャンネル"), "c/日本語チャンネル")
        self.assertEqual(normalize_account("youtube", "https://www.youtube.com/user/YouTube"), "user/youtube")
        self.assertEqual(normalize_account("youtube", "https://www.youtube.com/YouTubeCreators"), "custom/youtubecreators")
        with self.assertRaises(ValueError):
            normalize_account("youtube", "https://www.youtube.com/")
        with self.assertRaises(ValueError):
            normalize_account("youtube", "https://youtube.example/@channel")

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

    def test_youtube_handle_page_resolves_channel_id_without_api_data(self):
        channel_id = "UC1234567890123456789012"
        html = f'<html><script>var data={{"externalId":"{channel_id}"}}</script></html>'
        self.assertEqual(_youtube_channel_id_from_html(html), channel_id)
        self.assertIsNone(_youtube_channel_id_from_html('<html><title>Not found</title></html>'))
        self.assertEqual(
            YouTubeAdapter._public_channel_url("日本語チャンネル"),
            "https://www.youtube.com/@%E6%97%A5%E6%9C%AC%E8%AA%9E%E3%83%81%E3%83%A3%E3%83%B3%E3%83%8D%E3%83%AB",
        )
        self.assertEqual(YouTubeAdapter._public_channel_url("custom/YouTubeCreators"), "https://www.youtube.com/YouTubeCreators")
        self.assertEqual(
            YouTubeAdapter._public_channel_url(channel_id),
            f"https://www.youtube.com/channel/{channel_id}",
        )

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


class YouTubeAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_unclaimed_handle_falls_back_to_legacy_custom_url(self):
        import httpx

        channel_id = "UCTW2tw0Mhho72MojB1L48IQ"
        client = _YouTubeClient([
            ("@nobamangames", httpx.Response(404, request=httpx.Request("GET", "https://www.youtube.com/@nobamangames"))),
            ("/nobamangames", httpx.Response(200, text=f'<script>{{"externalId":"{channel_id}"}}</script>', request=httpx.Request("GET", "https://www.youtube.com/nobamangames"))),
        ])
        settings = SimpleNamespace(youtube_api_key=None, dashboard_base_url=None, social_webhook_secret=None)
        self.assertEqual(await YouTubeAdapter(settings, client)._resolve_channel_id("nobamangames"), channel_id)

    async def test_valid_channel_rss_404_is_retried_without_hard_failure(self):
        import httpx

        channel_id = "UClNdVSK1uy2xFHTaXZYXopw"
        feed_url = "https://www.youtube.com/feeds/videos.xml"
        page_url = f"https://www.youtube.com/channel/{channel_id}"
        client = _YouTubeClient([
            ("feeds/videos.xml", httpx.Response(404, request=httpx.Request("GET", feed_url))),
            (f"channel/{channel_id}", httpx.Response(200, text=f'<script>{{"externalId":"{channel_id}"}}</script>', request=httpx.Request("GET", page_url))),
        ])
        settings = SimpleNamespace(youtube_api_key=None, dashboard_base_url=None, social_webhook_secret=None)
        adapter = YouTubeAdapter(settings, client)
        adapter._yt_dlp_entries = AsyncMock(return_value=None)
        result = await adapter.poll(
            {"account_key": channel_id, "external_id": None, "handle": None, "cursor": {}, "display_name": None, "avatar_url": None},
            initialize=True,
        )
        self.assertEqual(result.status, "pending")
        self.assertFalse(result.cursor["feed_ready"])
        self.assertEqual(result.events, [])
        self.assertIn("代替経路を使用して再確認", result.error)

    async def test_rss_404_uses_public_metadata_fallback_without_api_key(self):
        import httpx

        channel_id = "UCTW2tw0Mhho72MojB1L48IQ"
        client = _YouTubeClient([
            ("feeds/videos.xml", httpx.Response(404, request=httpx.Request("GET", "https://www.youtube.com/feeds/videos.xml"))),
            (f"channel/{channel_id}", httpx.Response(200, text=f'<script>{{"externalId":"{channel_id}"}}</script>', request=httpx.Request("GET", f"https://www.youtube.com/channel/{channel_id}"))),
        ])
        settings = SimpleNamespace(youtube_api_key=None, dashboard_base_url=None, social_webhook_secret=None)
        adapter = YouTubeAdapter(settings, client)
        adapter._yt_dlp_entries = AsyncMock(return_value=([{"id": "video-1", "channel_id": channel_id, "title": "Video", "account": "Creator", "url": "https://www.youtube.com/watch?v=video-1", "published_at": ""}], "Creator"))
        result = await adapter.poll(
            {"account_key": channel_id, "external_id": channel_id, "handle": None, "cursor": {}, "display_name": None, "avatar_url": None},
            initialize=True,
        )
        self.assertEqual(result.status, "active")
        self.assertEqual(result.cursor["seen"], ["video-1"])
        self.assertEqual(result.display_name, "Creator")
        self.assertEqual(result.cursor["source"], "public_metadata")
        self.assertGreater(result.cursor["rss_retry_at"], int(time.time()))

    async def test_open_rss_circuit_skips_repeated_failing_request(self):
        channel_id = "UCTW2tw0Mhho72MojB1L48IQ"
        client = _YouTubeClient([])
        settings = SimpleNamespace(youtube_api_key=None, dashboard_base_url=None, social_webhook_secret=None)
        adapter = YouTubeAdapter(settings, client)
        adapter._yt_dlp_entries = AsyncMock(return_value=([{"id": "video-1", "channel_id": channel_id, "title": "Video", "account": "Creator", "url": "https://www.youtube.com/watch?v=video-1", "published_at": ""}], "Creator"))
        result = await adapter.poll(
            {"account_key": channel_id, "external_id": channel_id, "handle": None, "cursor": {"seen": ["video-1"], "feed_ready": True, "rss_retry_at": int(time.time()) + 3600, "rss_last_status": 404}, "display_name": "Creator", "avatar_url": None},
            initialize=False,
        )
        self.assertEqual(result.status, "active")
        self.assertEqual(result.cursor["source"], "public_metadata")
        self.assertEqual(client.responses, [])

    async def test_feed_recovery_sets_baseline_without_old_notifications(self):
        import httpx

        channel_id = "UClNdVSK1uy2xFHTaXZYXopw"
        atom = f"""<feed xmlns='http://www.w3.org/2005/Atom' xmlns:yt='http://www.youtube.com/xml/schemas/2015'><entry><yt:videoId>old-video</yt:videoId><yt:channelId>{channel_id}</yt:channelId><title>Old</title><link href='https://youtu.be/old-video'/><author><name>Creator</name></author></entry></feed>"""
        feed_url = "https://www.youtube.com/feeds/videos.xml"
        client = _YouTubeClient([("feeds/videos.xml", httpx.Response(200, text=atom, request=httpx.Request("GET", feed_url)))])
        settings = SimpleNamespace(youtube_api_key=None, dashboard_base_url=None, social_webhook_secret=None)
        result = await YouTubeAdapter(settings, client).poll(
            {"account_key": channel_id, "external_id": channel_id, "handle": None, "cursor": {"seen": [], "feed_ready": False}, "display_name": None, "avatar_url": None},
            initialize=False,
        )
        self.assertTrue(result.cursor["feed_ready"])
        self.assertEqual(result.cursor["seen"], ["old-video"])
        self.assertEqual(result.events, [])

    async def test_rss_404_uses_official_api_uploads_fallback(self):
        import httpx

        channel_id = "UClNdVSK1uy2xFHTaXZYXopw"
        request = lambda url: httpx.Request("GET", url)
        client = _YouTubeClient([
            ("feeds/videos.xml", httpx.Response(404, request=request("https://www.youtube.com/feeds/videos.xml"))),
            ("youtube/v3/channels", httpx.Response(200, json={"items": [{"snippet": {"title": "Creator", "thumbnails": {"default": {"url": "https://example.com/avatar.jpg"}}}, "contentDetails": {"relatedPlaylists": {"uploads": "UUUploads"}}}]}, request=request("https://www.googleapis.com/youtube/v3/channels"))),
            ("youtube/v3/playlistItems", httpx.Response(200, json={"items": [{"snippet": {"title": "Video", "channelTitle": "Creator", "publishedAt": "2026-01-01T00:00:00Z"}, "contentDetails": {"videoId": "video-1"}}]}, request=request("https://www.googleapis.com/youtube/v3/playlistItems"))),
            ("youtube/v3/videos", httpx.Response(200, json={"items": [{"id": "video-1", "snippet": {}}]}, request=request("https://www.googleapis.com/youtube/v3/videos"))),
        ])
        settings = SimpleNamespace(youtube_api_key="key", dashboard_base_url=None, social_webhook_secret=None)
        result = await YouTubeAdapter(settings, client).poll(
            {"account_key": channel_id, "external_id": channel_id, "handle": None, "cursor": {}, "display_name": None, "avatar_url": None},
            initialize=True,
        )
        self.assertEqual(result.status, "active")
        self.assertEqual(result.cursor["seen"], ["video-1"])
        self.assertEqual(result.display_name, "Creator")
        self.assertEqual(result.avatar_url, "https://example.com/avatar.jpg")
        self.assertEqual(result.events, [])

    async def test_websub_timeout_does_not_discard_successful_rss_poll(self):
        import httpx

        channel_id = "UCTW2tw0Mhho72MojB1L48IQ"
        atom = f"""<feed xmlns='http://www.w3.org/2005/Atom' xmlns:yt='http://www.youtube.com/xml/schemas/2015'><entry><yt:videoId>video-1</yt:videoId><yt:channelId>{channel_id}</yt:channelId><title>Video</title><link href='https://youtu.be/video-1'/><author><name>Creator</name></author></entry></feed>"""
        timeout_request = httpx.Request("POST", "https://pubsubhubbub.appspot.com/subscribe")
        client = _YouTubeClient([
            ("feeds/videos.xml", httpx.Response(200, text=atom, request=httpx.Request("GET", "https://www.youtube.com/feeds/videos.xml"))),
            ("pubsubhubbub.appspot.com", httpx.ReadTimeout("timed out", request=timeout_request)),
        ])
        settings = SimpleNamespace(youtube_api_key=None, dashboard_base_url="https://bot.example", social_webhook_secret="secret")
        result = await YouTubeAdapter(settings, client).poll(
            {"account_key": channel_id, "external_id": channel_id, "handle": None, "cursor": {}, "display_name": None, "avatar_url": None},
            initialize=True,
        )
        self.assertEqual(result.status, "degraded")
        self.assertEqual(result.cursor["seen"], ["video-1"])
        self.assertEqual(result.interval_seconds, 120)
        self.assertIn("RSS監視を継続", result.error)


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

    def test_resolved_targets_are_merged_by_provider_external_id(self):
        templates = default_templates("youtube", ["video"])
        first = self.storage.save_social_subscription_v2(1, "youtube", "nobamangames", 10, ["video"], {}, templates)
        first_target = self.storage.claim_social_targets("worker-a")[0]
        self.assertTrue(self.storage.complete_social_target(first_target["id"], "worker-a", status="active", cursor={"seen": ["v1"]}, next_check_at=int(time.time()) + 60, external_id="UCTW2tw0Mhho72MojB1L48IQ"))
        second = self.storage.save_social_subscription_v2(2, "youtube", "のばまんゲームス", 20, ["video"], {}, templates)
        second_target = next(item for item in self.storage.claim_social_targets("worker-b") if item["id"] == second["target_id"])
        self.assertTrue(self.storage.complete_social_target(second_target["id"], "worker-b", status="active", cursor={"seen": ["v1"]}, next_check_at=int(time.time()) + 60, external_id="UCTW2tw0Mhho72MojB1L48IQ"))
        self.assertEqual(len(self.storage.social_targets("youtube")), 1)
        self.assertEqual(self.storage.social_subscription(second["id"])["target_id"], first["target_id"])

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

    def test_old_subscription_is_not_imported_or_enabled_at_startup(self):
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
        self.assertEqual(item["events"], ["live"])
        self.assertIsNone(item["target_id"])
        self.assertEqual(item["templates"], {})
        self.assertFalse(migrated.module_enabled(1, "twitch_updates"))
        self.assertEqual(migrated.matching_social_subscriptions("twitch", "Creator", "live"), [])
        GuildStorage(path)
        self.assertEqual(len(migrated.social_targets("twitch")), 0)


if __name__ == "__main__":
    unittest.main()
