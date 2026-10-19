from db_support import prepare_database
import tempfile
import unittest
from pathlib import Path

from suggestions import SuggestionRepository, SuggestionService, SuggestionValidationError, normalize_settings


class SuggestionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.repository = SuggestionRepository(prepare_database(Path(self.directory.name) / "suggestions.sqlite3", self.addCleanup))
        self.service = SuggestionService(self.repository)

    def tearDown(self):
        self.directory.cleanup()

    def test_defaults_create_a_required_paragraph_field(self):
        settings = normalize_settings({})
        self.assertEqual(settings["form_fields"][0]["key"], "idea")
        self.assertTrue(settings["form_fields"][0]["required"])
        self.assertEqual(settings["form_fields"][0]["style"], "paragraph")

    def test_form_is_limited_to_five_fields(self):
        with self.assertRaises(SuggestionValidationError):
            normalize_settings({"form_fields": [{"key": str(index), "label": "Field", "max_length": 10} for index in range(6)]})

    def test_required_answer_is_validated(self):
        with self.assertRaises(ValueError):
            self.service.validate_answers(normalize_settings({}), {"idea": ""})

    def test_vote_can_be_changed_and_removed(self):
        settings = normalize_settings({"channel_id": 10})
        item = self.service.submit(1, 10, 20, settings, {"idea": "Improve onboarding"})
        item = self.service.vote(1, item["id"], 30, 1, settings)
        self.assertEqual((item["upvotes"], item["downvotes"]), (1, 0))
        item = self.service.vote(1, item["id"], 30, -1, settings)
        self.assertEqual((item["upvotes"], item["downvotes"]), (0, 1))
        item = self.service.vote(1, item["id"], 30, -1, settings)
        self.assertEqual((item["upvotes"], item["downvotes"]), (0, 0))

    def test_review_closes_voting(self):
        settings = normalize_settings({"channel_id": 10})
        item = self.service.submit(1, 10, 20, settings, {"idea": "Add a guide"})
        item = self.service.review(1, item["id"], 40, "approved", 'Accepted')
        self.assertEqual(item["status"], "approved")
        self.assertEqual(item["reviewer_id"], 40)
        with self.assertRaises(RuntimeError):
            self.service.vote(1, item["id"], 30, 1, settings)
        with self.assertRaises(RuntimeError):
            self.service.review(1, item["id"], 41, "rejected", 'Declined')
        self.assertEqual(self.repository.get(1, item["id"])["status"], "approved")

    def test_reason_history_implemented_and_revision_conflict_are_atomic(self):
        item = self.repository.create(1,10,20,{'idea':'Add guide'})
        for reason in ('', '   ', 'x'*1001):
            with self.assertRaisesRegex(ValueError,'invalid_reason'):
                self.repository.review(1,item['id'],40,'approved',reason)
        self.assertEqual(len(self.repository.events(1,item['id'])),1)
        with self.assertRaisesRegex(RuntimeError,'suggestion_closed'):
            self.service.review(1,item['id'],40,'implemented','Not approved')
        approved=self.service.review(1,item['id'],40,'approved','Useful',expected_revision=item['revision'])
        self.assertEqual(approved['review_reason'],'Useful')
        before=self.repository.events(1,item['id'])
        with self.assertRaisesRegex(RuntimeError,'revision_conflict'):
            self.service.review(1,item['id'],40,'implemented','Done',expected_revision=item['revision'])
        self.assertEqual(self.repository.events(1,item['id']),before)
        result=self.service.review(1,item['id'],40,'implemented','Released',expected_revision=approved['revision'])
        self.assertIsNotNone(result['implemented_at'])
        events=self.repository.events(1,item['id'],limit=1)
        self.assertEqual(events[0]['detail'],{'status':'implemented','previous_status':'approved','reason':'Released'})
        self.assertEqual(len(self.repository.events(1,item['id'],before=events[0]['id'])),2)
        with self.assertRaises(LookupError):self.repository.events(2,item['id'])
        with self.assertRaises(RuntimeError):self.repository.vote(1,item['id'],30,1)
        with self.assertRaises(RuntimeError):self.service.review(1,item['id'],40,'implemented','Again')
        with self.repository._connection() as connection:
            rows=connection.execute("SELECT payload_json FROM suggestion_outbox WHERE suggestion_id=%s AND action='review_log'",(item['id'],)).fetchall()
        self.assertEqual(len(rows),2)

    def test_disabled_voting_is_rejected(self):
        settings = normalize_settings({"channel_id": 10, "allow_voting": False})
        item = self.service.submit(1, 10, 20, settings, {"idea": "Add a guide"})
        with self.assertRaises(PermissionError):
            self.service.vote(1, item["id"], 30, 1, settings)

    def test_other_guild_cannot_read_vote_review_or_attach(self):
        item = self.repository.create(1, 10, 20, {"idea": "Private idea"})
        self.assertIsNone(self.repository.get(2, item["id"]))
        self.assertEqual(self.repository.list(2), [])
        for operation in (
            lambda: self.repository.vote(2, item["id"], 30, 1),
            lambda: self.repository.review(2, item["id"], 30, "approved", 'Cross guild'),
            lambda: self.repository.attach_message(2, item["id"], 100),
        ):
            with self.assertRaises(LookupError):
                operation()
        self.repository.mark_delivery_failed(2, item["id"], "failure")
        self.assertEqual(self.repository.get(1, item["id"])["status"], "pending")

    def test_delivery_failure_persists_and_closes_operations(self):
        item = self.repository.create(1, 10, 20, {"idea": "Idea"})
        self.repository.mark_delivery_failed(1, item["id"], "Forbidden")
        restarted = SuggestionRepository(prepare_database(self.repository.database_url, self.addCleanup))
        self.assertEqual(restarted.get(1, item["id"])["status"], "delivery_failed")
        with self.assertRaises(RuntimeError):
            restarted.vote(1, item["id"], 30, 1)
        with self.assertRaises(RuntimeError):
            restarted.review(1, item["id"], 30, "approved", 'After restart')

    def test_message_and_votes_survive_repository_restart(self):
        item = self.repository.create(1, 10, 20, {"idea": "Idea"})
        self.repository.attach_message(1, item["id"], 100)
        self.repository.vote(1, item["id"], 30, 1)
        restarted = SuggestionRepository(prepare_database(self.repository.database_url, self.addCleanup))
        restored = restarted.get(1, item["id"])
        self.assertEqual(restored["message_id"], 100)
        self.assertEqual(restored["upvotes"], 1)
        self.assertEqual(restarted.vote(1, item["id"], 30, 1)["upvotes"], 0)

    def test_review_row_lock_serializes_a_waiting_vote(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from database import connect
        item = self.repository.create(1, 10, 20, {'idea': 'Idea'})
        entered = Event()
        def vote():
            entered.set()
            return self.repository.vote(1, item['id'], 30, 1)
        with ThreadPoolExecutor(max_workers=1) as executor:
            with connect(self.repository.database_url) as c:
                c.execute("UPDATE suggestions SET status='approved' WHERE id=%s", (item['id'],))
                future = executor.submit(vote)
                self.assertTrue(entered.wait(5))
                self.assertFalse(future.done())
            with self.assertRaisesRegex(RuntimeError, 'suggestion_closed'):
                future.result(timeout=10)
        self.assertEqual(self.repository.get(1, item['id'])['upvotes'], 0)


if __name__ == "__main__":
    unittest.main()
