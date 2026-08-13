import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from automod.models import default_rule, validate_rule
from automod.service import ModerationService
from storage import GuildStorage


class AutoModStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = GuildStorage(Path(self.temp_dir.name) / "bot.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def keyword_rule():
        value = default_rule("keyword")
        value.update({"name": "words", "trigger_config": {"keywords": ["bad"], "allow_list": [], "match": "wildcard"}})
        return validate_rule(value)

    def test_rule_crud_updates_revision_and_is_guild_scoped(self):
        saved = self.storage.save_automod_rule(1, self.keyword_rule())
        first_revision = self.storage.get_module(1, "automod")["settings"]["rules_revision"]
        self.assertEqual(self.storage.automod_rule(1, saved["id"])["name"], "words")
        self.assertIsNone(self.storage.automod_rule(2, saved["id"]))
        saved["name"] = "updated"
        updated = self.storage.save_automod_rule(1, saved, saved["id"])
        self.assertEqual(updated["revision"], 2)
        self.assertGreater(self.storage.get_module(1, "automod")["settings"]["rules_revision"], first_revision)
        self.assertTrue(self.storage.delete_automod_rule(1, saved["id"]))
        self.assertFalse(self.storage.delete_automod_rule(1, saved["id"]))

    def test_points_expire_revoke_and_events_purge_evidence(self):
        event_id = self.storage.create_automod_event(1, None, 2, 3, 4, "keyword", "reason", "secret", [{"filename": "x.txt"}], "enforce", 1)
        self.assertIsNotNone(event_id)
        _, before, after = self.storage.add_points(1, 2, 2, "active", automod_event_id=event_id)
        self.storage.add_points(1, 2, 3, "expired", expires_at=int(time.time()) - 1)
        self.assertEqual((before, after, self.storage.active_points(1, 2)), (0, 2, 2))
        self.assertEqual(self.storage.revoke_points(1, 2), 2)
        self.assertEqual(self.storage.active_points(1, 2), 0)
        with self.storage._connection() as connection:
            connection.execute("UPDATE automod_events SET evidence_expires_at=0 WHERE id=?", (event_id,))
        self.assertEqual(self.storage.purge_automod_evidence(), 1)
        with self.storage._connection() as connection:
            event = connection.execute("SELECT evidence_text,attachments_json FROM automod_events WHERE id=?", (event_id,)).fetchone()
        self.assertIsNone(event["evidence_text"])
        self.assertEqual(json.loads(event["attachments_json"]), [])

    def test_duplicate_message_rule_event_is_ignored(self):
        saved = self.storage.save_automod_rule(1, self.keyword_rule())
        first = self.storage.create_automod_event(1, saved["id"], 2, 3, 4, "keyword", "reason", "text", [], "enforce")
        duplicate = self.storage.create_automod_event(1, saved["id"], 2, 3, 4, "keyword", "reason", "text", [], "enforce")
        self.assertIsInstance(first, int)
        self.assertIsNone(duplicate)

    def test_scheduled_actions_are_durable_and_idempotently_completed(self):
        action_id = self.storage.schedule_moderation_action(1, 2, "unban", 1, "done", None)
        self.assertEqual(self.storage.due_moderation_actions(now=2)[0]["id"], action_id)
        self.storage.complete_moderation_action(action_id)
        self.assertEqual(self.storage.due_moderation_actions(now=2), [])

    def test_legacy_migration_is_idempotent_and_preserves_warning_points(self):
        self.storage.set_module(1, "moderation", enabled=True, settings={"escalation_enabled": True, "escalation_threshold": 3,
            "escalation_action": "timeout", "escalation_timeout_minutes": 45})
        self.storage.set_module(1, "chat_filter", enabled=True, settings={"filter_keywords": "foo\nbar", "filter_regex": "b.z",
            "filter_action": "delete_warn", "safe_browsing_enabled": True})
        self.storage.set_module(1, "anti_spam", enabled=True, settings={"spam_window_seconds": 10, "spam_message_limit": 5,
            "spam_mention_limit": 8, "spam_duplicate_limit": 3, "spam_action": "timeout", "spam_timeout_minutes": 15})
        with self.storage._connection() as connection:
            connection.execute("INSERT INTO guild_users(guild_id,user_id,warn) VALUES(1,9,2)")
        self.assertEqual(self.storage.migrate_legacy_automod(["legacy"]), 1)
        self.assertEqual(self.storage.migrate_legacy_automod(["legacy"]), 0)
        rules = self.storage.automod_rules(1)
        self.assertEqual(len(rules), 7)
        self.assertEqual(len({item["name"] for item in rules}), 7)
        self.assertEqual(rules[0]["trigger_config"]["match"], "contains")
        self.assertEqual(self.storage.active_points(1, 9), 2)
        settings = self.storage.get_module(1, "automod")["settings"]
        self.assertEqual(settings["point_thresholds"][0]["action"]["duration_minutes"], 45)

    def test_v2_migration_splits_families_and_keeps_links(self):
        self.storage.set_module(1,"automod",enabled=True)
        keyword = self.storage.save_automod_rule(1,self.keyword_rule())
        spam = default_rule("message_rate")
        spam.update({"name":"spam","mode":"enforce","actions":[{"type":"delete"}]})
        spam = self.storage.save_automod_rule(1,validate_rule(spam))
        event = self.storage.create_automod_event(1,keyword["id"],2,3,4,"keyword","reason","body",[],"enforce")
        self.storage.add_case(1,2,"warn","reason",automod_event_id=event,rule_id=keyword["id"])
        self.assertEqual(self.storage.migrate_moderation_v2(),1)
        self.assertEqual(self.storage.migrate_moderation_v2(),0)
        self.assertEqual({item["family"] for item in self.storage.moderation_rules(1)},{"automod","anti_spam"})
        case = self.storage.recent_cases(1,2)[0]
        self.assertEqual(case["moderation_event_id"],event)
        self.assertIsNotNone(case["moderation_rule_id"])

    def test_generic_events_actions_lockdown_and_queue_are_durable(self):
        rule = self.storage.save_moderation_rule(1,{**self.keyword_rule(),"family":"automod","event_type":"message_create"})
        event = self.storage.create_moderation_event(1,family="automod",event_type="message_create",source="automod",
            reason="reason",rule_id=rule["id"],actor_id=2,target_user_id=2,target_id=4,dedupe_key="one")
        self.storage.finish_moderation_event(event,[{"type":"points","status":"success","case_id":9,"before":0,"after":1}])
        with self.storage._connection() as connection:
            stored = connection.execute("SELECT case_id FROM moderation_events WHERE id=?",(event,)).fetchone()
            action = connection.execute("SELECT action_type,status FROM moderation_action_results WHERE event_id=?",(event,)).fetchone()
        self.assertEqual(stored["case_id"],9)
        self.assertEqual(tuple(action),("points","success"))
        lockdown = self.storage.start_lockdown(1,reason="raid",started_by=3,unlock_at=10,source_event_id=event)
        self.storage.save_lockdown_snapshot(lockdown,20,1,{"send_messages":None},{"send_messages":False})
        self.assertEqual(self.storage.due_lockdowns(10)[0]["id"],lockdown)
        self.assertEqual(self.storage.lockdown_snapshots(lockdown)[0]["before"]["send_messages"],None)
        request = self.storage.enqueue_moderation_action(1,3,"warn",target_user_id=2,reason="manual",dedupe_key="request-one")
        self.assertIsNotNone(request)
        self.assertIsNone(self.storage.enqueue_moderation_action(1,3,"warn",target_user_id=2,reason="manual",dedupe_key="request-one"))
        self.assertEqual(self.storage.pending_moderation_actions()[0]["id"],request)

    def test_raid_state_becomes_stale_and_can_be_cleared(self):
        self.storage.set_raid_state(42, True, source_rule_id=7)
        stale = self.storage.stale_raid_states(int(time.time()) + 1)
        self.assertEqual(stale[0]["guild_id"], 42)
        self.assertEqual(stale[0]["source_rule_id"], 7)
        self.storage.set_raid_state(42, False)
        self.assertEqual(self.storage.stale_raid_states(int(time.time()) + 1), [])


class ModerationThresholdTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = GuildStorage(Path(self.temp_dir.name) / "bot.sqlite3")
        self.service = ModerationService(None, self.storage)
        settings = self.storage.get_module(1, "automod")["settings"]
        settings["point_thresholds"] = [
            {"points": 3, "action": {"type": "timeout", "duration_minutes": 10}},
            {"points": 5, "action": {"type": "ban"}},
        ]
        self.storage.set_module(1, "automod", enabled=True, settings=settings)

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_only_highest_newly_crossed_threshold_runs(self):
        self.service.apply_case = AsyncMock(return_value=99)
        result = await self.service._apply_threshold(SimpleNamespace(id=1), object(), 2, 6, "points", 10, 20)
        self.assertEqual(result["action"], "ban")
        self.assertEqual(result["points"], 5)
        self.service.apply_case.assert_awaited_once()
        self.service.apply_case.reset_mock()
        self.assertIsNone(await self.service._apply_threshold(SimpleNamespace(id=1), object(), 5, 6, "points", 10, 20))
        self.service.apply_case.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
