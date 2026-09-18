import tempfile
import unittest
from pathlib import Path

from db_support import prepare_database
from guild_settings import GuildSettingsRepository
from guild_settings.models import welcome_settings, moderation_settings


class GuildSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = prepare_database(Path(self.temp.name) / 'test.db', self.addCleanup)
        self.repository = GuildSettingsRepository(self.path)

    def test_guild_isolation_toggle_and_revision_survive_restart(self):
        saved = self.repository.set_module(1, 'welcome', enabled=True,
            settings={'welcome_channel_id': 10, 'welcome_enabled': True}, expected_revision=0)
        self.assertEqual(saved['revision'], 1)
        self.assertEqual(self.repository.get_module(2, 'welcome')['revision'], 0)
        self.assertFalse(self.repository.module_enabled(2, 'welcome'))
        disabled = self.repository.set_module(1, 'welcome', enabled=False, expected_revision=1)
        self.assertEqual(disabled['settings'], saved['settings'])
        restarted = GuildSettingsRepository(self.path)
        self.assertEqual(restarted.get_module(1, 'welcome'), disabled)
        with self.assertRaisesRegex(RuntimeError, 'revision_conflict'):
            restarted.set_module(1, 'welcome', enabled=True, expected_revision=1)
        self.assertEqual(restarted.get_module(1, 'welcome'), disabled)

    def test_normalization_is_independent_of_database_and_does_not_mutate_input(self):
        value = {'welcome_content': ' ', 'welcome_channel_id': None}
        normalized = welcome_settings(value)
        self.assertEqual(value, {'welcome_content': ' ', 'welcome_channel_id': None})
        self.assertTrue(normalized['welcome_content'].strip())
        self.assertFalse(normalized['welcome_enabled'])
        self.assertIsNone(normalized['welcome_channel_id'])
        rules = moderation_settings({'immune_user_ids': ['2', '2', 'invalid'], 'evidence_retention_days': 999})
        self.assertEqual(rules['immune_user_ids'], [2])
        self.assertEqual(rules['evidence_retention_days'], 365)
