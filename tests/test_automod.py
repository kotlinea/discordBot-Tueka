import asyncio
import statistics
import time
import unittest
from datetime import datetime, timedelta, timezone

from automod.engine import AutoModEngine, MessageContext
from automod.models import default_rule, validate_rule


def rule(trigger_type: str, config: dict, **values):
    raw = default_rule(trigger_type)
    raw.update({"name": trigger_type, "mode": "monitor", "trigger_config": config, **values})
    return {**validate_rule(raw), "id": values.get("id", 1)}


class AutoModValidationTests(unittest.TestCase):
    def test_scope_policy_prevents_conflicting_channel_and_role_lists(self):
        raw = default_rule("keyword")
        raw.update({"name": "scope", "trigger_config": {"keywords": ["bad"]}, "conditions": {"channel_policy": "only", "role_policy": "all_except", "channel_ids": [10], "required_role_ids": [20]}, "exemptions": {"channel_ids": [11], "role_ids": [21]}, "actions": [{"type": "log"}]})
        validated = validate_rule(raw)
        self.assertEqual(validated["conditions"]["channel_ids"], [10])
        self.assertEqual(validated["conditions"]["required_role_ids"], [])
        self.assertEqual(validated["exemptions"]["channel_ids"], [])
        self.assertEqual(validated["exemptions"]["role_ids"], [21])
        with self.assertRaises(ValueError):
            validate_rule({**raw, "conditions": {"channel_policy": "only", "channel_ids": []}})

    def test_configurable_actions_keep_their_options(self):
        raw = default_rule("keyword")
        raw.update({"name": "actions", "trigger_config": {"keywords": ["bad"]}, "actions": [{"type": "points", "points": 3, "expires_days": 7}, {"type": "tempban", "duration_minutes": 120}, {"type": "log", "message": "{rule}: {reason}"}]})
        actions = validate_rule(raw)["actions"]
        self.assertEqual(actions[0], {"type": "points", "points": 3, "expires_days": 7})
        self.assertEqual(actions[1], {"type": "tempban", "duration_minutes": 120})
        self.assertEqual(actions[2], {"type": "log", "message": "{rule}: {reason}"})

    def test_terminal_actions_are_mutually_exclusive(self):
        raw = default_rule("keyword")
        raw.update({"trigger_config": {"keywords": ["bad"]}, "actions": [{"type": "kick"}, {"type": "ban"}]})
        with self.assertRaises(ValueError):
            validate_rule(raw)

    def test_invalid_resources_and_regex_are_rejected(self):
        raw = default_rule("honeypot")
        raw["trigger_config"] = {"channel_ids": [-1]}
        with self.assertRaises(ValueError):
            validate_rule(raw)

    def test_trigger_family_and_event_are_typed(self):
        raid = validate_rule(default_rule("join_rate"))
        self.assertEqual((raid["family"], raid["event_type"]), ("anti_raid", "member_join"))
        raid["family"] = "automod"
        with self.assertRaises(ValueError):
            validate_rule(raid)
        raw = default_rule("regex")
        raw["trigger_config"] = {"patterns": ["("]}
        with self.assertRaises(ValueError):
            validate_rule(raw)


class AutoModEngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_keyword_matching_unicode_wildcard_and_allow_list(self):
        engine = AutoModEngine()
        keyword = rule("keyword", {"keywords": ["禁止語", "sp*m"], "allow_list": ["許可された禁止語"], "match": "wildcard"})
        self.assertTrue(await engine.evaluate(MessageContext(1, 2, 3, "これは禁止語です"), [keyword]))
        self.assertTrue(await engine.evaluate(MessageContext(1, 2, 3, "SPOOOOM"), [keyword]))
        self.assertFalse(await engine.evaluate(MessageContext(1, 2, 3, "許可された禁止語です"), [keyword]))
        latin = rule("keyword", {"keywords": ["bad"], "allow_list": [], "match": "wildcard"})
        self.assertFalse(await engine.evaluate(MessageContext(1, 2, 3, "badminton"), [latin]))
        contains = rule("keyword", {"keywords": ["禁止語"], "allow_list": [], "match": "contains"})
        self.assertTrue(await engine.evaluate(MessageContext(1, 2, 3, "禁止語彙"), [contains]))

    async def test_domain_boundary_idn_invites_and_www_urls(self):
        engine = AutoModEngine()
        blocked = rule("domain", {"mode": "blacklist", "domains": ["example.com", "例え.テスト"]})
        self.assertTrue(await engine.evaluate(MessageContext(1, 2, 3, "https://sub.example.com/a"), [blocked]))
        self.assertFalse(await engine.evaluate(MessageContext(1, 2, 3, "https://notexample.com"), [blocked]))
        self.assertTrue(await engine.evaluate(MessageContext(1, 2, 3, "https://例え.テスト/path"), [blocked]))
        allowed = rule("domain", {"mode": "block_all_except", "domains": ["example.com"]})
        self.assertFalse(await engine.evaluate(MessageContext(1, 2, 3, "www.example.com/image.png"), [allowed]))
        invite = rule("discord_invite", {})
        self.assertTrue(await engine.evaluate(MessageContext(1, 2, 3, "discord.gg/example"), [invite]))

    async def test_global_and_rule_exemptions_and_all_conditions(self):
        engine = AutoModEngine()
        configured = rule("keyword", {"keywords": ["bad"], "allow_list": [], "match": "wildcard"},
            conditions={"channel_ids": [3], "required_role_ids": [10], "excluded_role_ids": [11],
                        "minimum_account_age_days": 7, "minimum_join_age_days": 1},
            exemptions={"user_ids": [99], "role_ids": [12], "channel_ids": [4]})
        now = datetime.now(timezone.utc)
        context = MessageContext(1, 2, 3, "bad", role_ids={10}, account_created_at=now - timedelta(days=8), joined_at=now - timedelta(days=2))
        self.assertTrue(await engine.evaluate(context, [configured]))
        context.role_ids.add(11)
        self.assertFalse(await engine.evaluate(context, [configured]))
        self.assertTrue(engine.globally_exempt(MessageContext(1, 2, 3, role_ids={50}), {"immune_role_ids": [50]}))
        self.assertTrue(engine.globally_exempt(MessageContext(1, 2, 3, category_id=20), {"immune_channel_ids": [20]}))
        exempt_user = MessageContext(1, 99, 3, "bad", role_ids={10}, account_created_at=now - timedelta(days=8), joined_at=now - timedelta(days=2))
        self.assertFalse(await engine.evaluate(exempt_user, [configured]))

    async def test_rate_detectors_skip_edits_and_prune_idle_state(self):
        engine = AutoModEngine(max_state_keys=3)
        rate = rule("message_rate", {"limit": 2, "window_seconds": 10})
        first = MessageContext(1, 2, 3, "one", now=100.0)
        self.assertFalse(await engine.evaluate(first, [rate]))
        self.assertFalse(await engine.evaluate(MessageContext(1, 2, 3, "edited", now=101.0), [rate], edited=True))
        self.assertTrue(await engine.evaluate(MessageContext(1, 2, 3, "two", now=102.0), [rate]))
        engine.prune(1000.0, max_age=10)
        self.assertEqual(engine.state_size, 0)

    async def test_caps_media_honeypot_priority_and_stop(self):
        engine = AutoModEngine()
        caps = rule("caps", {"percentage": 70, "minimum_letters": 5}, id=2, priority=20)
        honey = rule("honeypot", {"channel_ids": [3]}, id=1, priority=10, stop_on_match=True)
        matches = await engine.evaluate(MessageContext(1, 2, 3, "LOUD TEXT"), [caps, honey])
        self.assertEqual([item.rule["trigger_type"] for item in matches], ["honeypot"])
        media = rule("media_only", {"allow_links": True})
        self.assertFalse(await engine.evaluate(MessageContext(1, 2, 4, "www.example.com/file.png"), [media]))
        self.assertTrue(await engine.evaluate(MessageContext(1, 2, 4, "hello"), [media]))

    async def test_safe_browsing_checker_is_optional_and_bounded(self):
        seen = []

        async def checker(urls):
            seen.extend(urls)
            return urls[0]

        unsafe = rule("safe_browsing", {})
        context = MessageContext(1, 2, 3, " ".join(f"https://x{i}.test" for i in range(8)))
        self.assertTrue(await AutoModEngine().evaluate(context, [unsafe], unsafe_url_checker=checker))
        self.assertEqual(len(seen), 5)

    async def test_bot_is_only_evaluated_when_explicitly_scoped(self):
        engine = AutoModEngine()
        ordinary = rule("message_rate", {"limit": 1, "window_seconds": 10})
        bot_context = MessageContext(1, 99, 3, "spam", actor_kind="bot")
        self.assertFalse(await engine.evaluate(bot_context, [ordinary]))
        scoped = {**ordinary, "conditions": {**ordinary["conditions"], "bot_ids": [99], "actor_kinds": ["bot"]}}
        self.assertTrue(await engine.evaluate(bot_context, [scoped]))

    async def test_reaction_raid_emoji_and_phishing_triggers(self):
        engine = AutoModEngine()
        reaction = rule("reaction_burst", {"limit": 2, "window_seconds": 10})
        first = MessageContext(1,2,3,event_type="reaction_add",target_id=50,now=1)
        self.assertFalse(await engine.evaluate(first,[reaction]))
        self.assertTrue(await engine.evaluate(MessageContext(1,2,3,event_type="reaction_add",target_id=50,now=2),[reaction]))
        raid = rule("join_rate", {"limit": 2, "window_seconds": 30})
        self.assertFalse(await engine.evaluate(MessageContext(1,10,0,event_type="member_join",now=10),[raid]))
        self.assertTrue(await engine.evaluate(MessageContext(1,11,0,event_type="member_join",now=11),[raid]))
        recent = rule("new_member_activity", {"join_age_minutes": 10})
        self.assertTrue(await engine.evaluate(MessageContext(1,12,3,"hello",joined_at=datetime.now(timezone.utc) - timedelta(minutes=2)),[recent]))
        self.assertFalse(await engine.evaluate(MessageContext(1,12,3,"hello",joined_at=datetime.now(timezone.utc) - timedelta(minutes=20)),[recent]))
        symbols = rule("emoji_sticker_rate", {"limit": 10, "window_seconds": 10, "per_message_limit": 3})
        self.assertTrue(await engine.evaluate(MessageContext(1,2,3,"😀😀😀"),[symbols]))
        phishing = rule("phishing_link", {})
        self.assertTrue(await engine.evaluate(MessageContext(1,2,3,"[example.com](https://evil.test/login)"),[phishing]))

    async def test_cached_hundred_rule_evaluation_p95_is_under_20ms(self):
        engine = AutoModEngine()
        rules = [rule("keyword", {"keywords": [f"blocked-{index}"], "allow_list": [], "match": "wildcard"}, id=index) for index in range(100)]
        context = MessageContext(1, 2, 3, "ordinary message")
        await engine.evaluate(context, rules)
        samples = []
        for _ in range(100):
            started = time.perf_counter()
            await engine.evaluate(context, rules)
            samples.append(time.perf_counter() - started)
        p95 = statistics.quantiles(samples, n=20)[18]
        self.assertLess(p95, 0.020, f"p95 was {p95 * 1000:.2f}ms")


if __name__ == "__main__":
    unittest.main()
