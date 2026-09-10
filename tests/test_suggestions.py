import tempfile
import unittest
from pathlib import Path

from suggestions import SuggestionRepository, SuggestionService, SuggestionValidationError, normalize_settings


class SuggestionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.repository = SuggestionRepository(Path(self.directory.name) / "suggestions.sqlite3")
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
        item = self.service.review(1, item["id"], 40, "approved")
        self.assertEqual(item["status"], "approved")
        self.assertEqual(item["reviewer_id"], 40)
        with self.assertRaises(RuntimeError):
            self.service.vote(1, item["id"], 30, 1, settings)
        with self.assertRaises(RuntimeError):
            self.service.review(1, item["id"], 41, "rejected")
        self.assertEqual(self.repository.get(1, item["id"])["status"], "approved")

    def test_disabled_voting_is_rejected(self):
        settings = normalize_settings({"channel_id": 10, "allow_voting": False})
        item = self.service.submit(1, 10, 20, settings, {"idea": "Add a guide"})
        with self.assertRaises(PermissionError):
            self.service.vote(1, item["id"], 30, 1, settings)


if __name__ == "__main__":
    unittest.main()
