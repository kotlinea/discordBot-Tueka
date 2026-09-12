from db_support import prepare_database
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from automod.models import default_rule, validate_rule
from automod.service import ActionContext, ModerationService
from storage import GuildStorage


class AutoModStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = GuildStorage(prepare_database(Path(self.temp_dir.name) / "bot.sqlite3"))

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def keyword_rule():
        value = default_rule("keyword")
        value.update({"name": "words", "trigger_config": {"keywords": ["bad"], "allow_list": [], "match": "wildcard"}})
        return validate_rule(value)

    def test_rule_crud_updates_revision_and_is_guild_scoped(self):
        saved = self.storage.save_moderation_rule(1, self.keyword_rule())
        first_revision = self.storage.get_module(1, "moderation")["settings"]["rules_revision"]
        self.assertEqual(self.storage.moderation_rule(1, saved["id"])["name"], "words")
        self.assertIsNone(self.storage.moderation_rule(2, saved["id"]))
        saved["name"] = "updated"
        updated = self.storage.save_moderation_rule(1, saved, saved["id"])
        self.assertEqual(updated["revision"], 2)
        self.assertGreater(self.storage.get_module(1, "moderation")["settings"]["rules_revision"], first_revision)
        self.assertTrue(self.storage.delete_moderation_rule(1, saved["id"]))
        self.assertFalse(self.storage.delete_moderation_rule(1, saved["id"]))

    def test_rule_order_and_stop_flag_are_saved_together(self):
        first = self.storage.save_moderation_rule(1, {**self.keyword_rule(), "name": "first"})
        second = self.storage.save_moderation_rule(1, {**self.keyword_rule(), "name": "second"})
        ordered = self.storage.reorder_moderation_rules(1, "automod", [
            {"id": second["id"], "revision": second["revision"], "stop_on_match": True},
            {"id": first["id"], "revision": first["revision"], "stop_on_match": False},
        ])
        self.assertEqual([item["id"] for item in ordered], [second["id"], first["id"]])
        self.assertTrue(ordered[0]["stop_on_match"])
        with self.assertRaises(RuntimeError):
            self.storage.reorder_moderation_rules(1, "automod", [{"id": first["id"], "revision": first["revision"], "stop_on_match": False}])

    def test_points_expire_revoke_and_events_purge_evidence(self):
        event_id = self.storage.create_moderation_event(1, family="automod", event_type="message_create", source="automod", reason="reason", target_user_id=2, channel_id=3, target_id=4, evidence_text="secret", evidence={"attachments": [{"filename": "x.txt"}]})
        self.assertIsNotNone(event_id)
        _, before, after = self.storage.add_points(1, 2, 2, "active", moderation_event_id=event_id)
        self.storage.add_points(1, 2, 3, "expired", expires_at=int(time.time()) - 1)
        self.assertEqual((before, after, self.storage.active_points(1, 2)), (0, 2, 2))
        self.assertEqual(self.storage.revoke_points(1, 2), 2)
        self.assertEqual(self.storage.active_points(1, 2), 0)
        with self.storage._connection() as connection:
            connection.execute("UPDATE moderation_events SET evidence_expires_at=0 WHERE id=?", (event_id,))
        self.assertEqual(self.storage.purge_moderation_evidence(), 1)
        with self.storage._connection() as connection:
            event = connection.execute("SELECT evidence_text,evidence_json FROM moderation_events WHERE id=?", (event_id,)).fetchone()
        self.assertIsNone(event["evidence_text"])
        self.assertEqual(json.loads(event["evidence_json"]), {})

    def test_duplicate_message_rule_event_is_ignored(self):
        saved = self.storage.save_moderation_rule(1, self.keyword_rule())
        first = self.storage.create_moderation_event(1, family="automod", event_type="message_create", source="automod", reason="reason", rule_id=saved["id"], target_user_id=2, channel_id=3, target_id=4, dedupe_key="one")
        duplicate = self.storage.create_moderation_event(1, family="automod", event_type="message_create", source="automod", reason="reason", rule_id=saved["id"], target_user_id=2, channel_id=3, target_id=4, dedupe_key="one")
        self.assertIsInstance(first, int)
        self.assertIsNone(duplicate)

    def test_scheduled_actions_are_durable_and_idempotently_completed(self):
        action_id = self.storage.schedule_moderation_action(1, 2, "unban", 1, "done", None)
        self.assertEqual(self.storage.due_moderation_actions(now=2)[0]["id"], action_id)
        self.storage.complete_moderation_action(action_id)
        self.assertEqual(self.storage.due_moderation_actions(now=2), [])



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
        self.storage = GuildStorage(prepare_database(Path(self.temp_dir.name) / "bot.sqlite3"))
        self.service = ModerationService(None, self.storage)
        settings = self.storage.get_module(1, "infractions")["settings"]
        settings["point_thresholds"] = [
            {"points": 3, "action": {"type": "timeout", "duration_minutes": 10}},
            {"points": 5, "action": {"type": "ban"}},
        ]
        self.storage.set_module(1, "infractions", enabled=True, settings=settings)

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

    async def test_disabled_infractions_never_falls_back_to_old_thresholds(self):
        self.storage.set_module(1, 'infractions', enabled=False)
        self.storage.set_module(1, 'automod', enabled=True, settings={'point_thresholds': [
            {'points': 1, 'action': {'type': 'ban'}},
        ]})
        self.storage.set_module(1, 'moderation', enabled=True, settings={
            'escalation_enabled': True, 'escalation_threshold': 1, 'escalation_action': 'ban',
        })
        self.service.apply_case = AsyncMock()
        self.assertIsNone(await self.service._apply_threshold(SimpleNamespace(id=1), object(), 0, 5, 'points', None, None))
        self.service.apply_case.assert_not_awaited()

    async def test_points_action_records_only_current_rule_and_event_links(self):
        rule = self.storage.save_moderation_rule(1, validate_rule({**default_rule('keyword'),
            'mode': 'enforce', 'trigger_config': {'keywords': ['bad']}, 'actions': [{'type': 'points', 'points': 1}]}))
        event = self.storage.create_moderation_event(1, family='automod', event_type='message_create',
            source='automod', reason='rule', rule_id=rule['id'])
        context = ActionContext(SimpleNamespace(id=1), SimpleNamespace(id=2))
        results = await self.service.execute_actions(context, rule, 'rule', event, {})
        self.assertEqual(results[0]['status'], 'success', results)
        case = self.storage.recent_cases(1, 2)[0]
        self.assertEqual(case['moderation_rule_id'], rule['id'])
        self.assertEqual(case['moderation_event_id'], event)
        self.assertEqual(self.storage.active_points(1, 2), 1)


if __name__ == "__main__":
    unittest.main()
