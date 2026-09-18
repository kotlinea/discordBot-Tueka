import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from dashboard.repository import DashboardRepository
from db_support import prepare_database


class DashboardRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = prepare_database(Path(self.temp.name) / 'test.db', self.addCleanup)
        self.repository = DashboardRepository(self.path)

    def test_session_expiry_revocation_and_restart(self):
        with patch('dashboard.repository.time.time', return_value=1000):
            self.repository.create_dashboard_session('one', 'token-one', 10)
            self.repository.create_dashboard_session('two', 'token-two', 20)
        restarted = DashboardRepository(self.path)
        with patch('dashboard.repository.time.time', return_value=1010):
            self.assertIsNone(restarted.dashboard_session_token('one'))
            self.assertEqual(restarted.dashboard_session_token('two'), 'token-two')
            restarted.delete_dashboard_session('two')
            self.assertIsNone(self.repository.dashboard_session_token('two'))

    def test_oauth_state_is_expiring_and_consumed_once_concurrently(self):
        with patch('dashboard.repository.time.time', return_value=1000):
            self.repository.create_oauth_state('expired', 0)
            self.assertFalse(self.repository.consume_oauth_state('expired'))
            self.repository.create_oauth_state('active', 100)
            with ThreadPoolExecutor(max_workers=2) as workers:
                result = list(workers.map(lambda _: self.repository.consume_oauth_state('active'), range(2)))
            self.assertEqual(sorted(result), [False, True])

    def test_preferences_are_user_scoped_persisted_and_revision_checked(self):
        values = dict(locale='en', appearance='community', color_scheme='dark', navigation_collapsed=True)
        saved = self.repository.set_dashboard_preferences(1, expected_revision=0, **values)
        self.assertEqual(saved, {**values, 'revision': 1})
        restarted = DashboardRepository(self.path)
        self.assertEqual(restarted.dashboard_preferences(1), saved)
        self.assertEqual(restarted.dashboard_preferences(2)['revision'], 0)
        with self.assertRaisesRegex(RuntimeError, 'revision_conflict'):
            restarted.set_dashboard_preferences(1, expected_revision=0, **values)
        self.assertEqual(restarted.dashboard_preferences(1), saved)
