import unittest
from unittest.mock import MagicMock

from insights.service import InsightsService


class InsightsServiceTests(unittest.TestCase):
    def setUp(self):
        self.repo = MagicMock()
        self.service = InsightsService(self.repo, owner='generated-owner')

    def test_message_boundary_contains_only_ids_and_timestamp(self):
        self.service.message(1, 100, 20, 500)
        self.repo.event.assert_called_once_with(1, 'generated-owner', 'messages', '100', channel=20, occurred_at=500)
        self.assertFalse(self.service.message(1, 101, 20, 500, bot=True))
        self.assertEqual(self.repo.event.call_count, 1)

    def test_membership_requires_known_join_time_and_filters_bots(self):
        self.assertFalse(self.service.membership(1, 30, None, joining=False))
        self.assertFalse(self.service.membership(1, 30, 10, joining=True, bot=True))
        self.repo.event.assert_not_called()
        self.service.membership(1, 30, 10, joining=True)
        args = self.repo.event.call_args.args
        self.assertEqual(args[:3], (1, 'generated-owner', 'joins'))
        self.assertEqual(len(args[3]), 64)
        with self.assertRaises(ValueError):
            self.service.membership(1, 30, 10, joining=1)

    def test_observer_and_voice_operations_keep_same_process_owner(self):
        self.service.claim(1)
        self.service.heartbeat(1, {30: 20})
        self.service.voice(1, 30, 20, 21)
        self.assertFalse(self.service.voice(1, 31, 20, 21, bot=True))
        self.service.release(1)
        self.repo.claim.assert_called_once_with(1, 'generated-owner')
        self.repo.heartbeat.assert_called_once_with(1, 'generated-owner', {30: 20})
        self.repo.voice_change.assert_called_once_with(1, 'generated-owner', 30, 20, 21)
        self.repo.release.assert_called_once_with(1, 'generated-owner')
