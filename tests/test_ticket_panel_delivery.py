import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from db_support import prepare_database
from discord_io import DiscordFailure
from ticketing import TicketRepository
from ticketing.panel_delivery import PanelDeliveryService


class PanelPort:
    def __init__(self):
        self.messages = {}
        self.sent = 0
        self.deleted = []
        self.fail_delete = False

    async def publish_panel(self, config, panels, *, recover):
        if config['id'] in self.messages:
            return self.messages[config['id']]
        if recover:
            raise DiscordFailure('unknown receipt', partial=True)
        self.sent += 1
        self.messages[config['id']] = 900 + self.sent
        return 900 + self.sent

    async def find_panel_message(self, config):
        if config['id'] not in self.messages:
            raise DiscordFailure('unknown receipt', partial=True)
        return self.messages[config['id']]

    async def delete_panel_message(self, guild_id, channel_id, message_id):
        if self.fail_delete:
            raise DiscordFailure('temporary failure', retry=True)
        self.deleted.append(message_id)


class PanelDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = TicketRepository(prepare_database(Path(self.temp.name) / 'panel.db'))
        team = self.repo.save_team(1, {'name': 'Staff', 'role_ids': [500]})
        panel = self.repo.save_panel(1, {'name': 'Support', 'mode': 'channel', 'category_id': 100, 'team_id': team['id']})
        self.config = self.repo.save_panel_message(1, {'name': 'Support', 'channel_id': 10,
            'title': 'Support', 'panel_ids': [panel['id']]})
        self.port = PanelPort()
        self.service = PanelDeliveryService(self.repo, self.port)

    async def test_restart_recovers_sent_message_after_database_failure(self):
        with patch('ticketing.repository.time.time', return_value=1000):
            claim = self.repo.claim_panel_messages('worker', lease_seconds=1)[0]
            with patch.object(self.repo, 'mark_panel_published', side_effect=RuntimeError('database failed')):
                with self.assertRaises(RuntimeError):
                    await self.service.deliver(claim)
        with patch('ticketing.repository.time.time', return_value=1002):
            restarted = self.repo.claim_panel_messages('worker')[0]
            self.assertNotEqual(claim['lease_owner'], restarted['lease_owner'])
            self.assertFalse(self.repo.mark_panel_published(claim, 999))
            await self.service.deliver(restarted)
        self.assertEqual(self.port.sent, 1)
        self.assertEqual(self.repo.panel_message(1, self.config['id'])['status'], 'published')

    async def test_cleanup_failure_retains_both_message_ids_until_retry(self):
        claim = self.repo.claim_panel_messages('worker')[0]
        await self.service.deliver(claim)
        config = self.repo.panel_message(1, self.config['id'])
        config['channel_id'] = 11
        self.repo.save_panel_message(1, config, config['id'], config['revision'])
        self.port.messages.clear()
        self.port.fail_delete = True
        await self.service.deliver(self.repo.claim_panel_messages('worker')[0])
        saved = self.repo.panel_message(1, config['id'])
        self.assertEqual(saved['message_id'], 902)
        self.assertEqual(saved['previous_message_id'], 901)
        self.assertEqual(saved['status'], 'publishing')
        self.port.fail_delete = False
        await self.service.deliver(self.repo.claim_panel_messages('worker')[0])
        self.assertEqual(self.port.sent, 2)
        self.assertEqual(self.port.deleted, [901])
        self.assertIsNone(self.repo.panel_message(1, config['id'])['previous_message_id'])

    async def test_unknown_receipt_is_preserved_without_duplicate_send(self):
        with patch('ticketing.repository.time.time', return_value=1000):
            self.repo.claim_panel_messages('worker', lease_seconds=1)
        with patch('ticketing.repository.time.time', return_value=1002):
            await self.service.deliver(self.repo.claim_panel_messages('worker')[0])
        self.assertEqual(self.port.sent, 0)
        self.assertEqual(self.repo.panel_message(1, self.config['id'])['status'], 'publishing')

    async def test_edit_during_unknown_delivery_preserves_recovery_and_fences_old_revision(self):
        claim = self.repo.claim_panel_messages('worker')[0]
        saved = self.repo.panel_message(1, self.config['id'])
        saved['title'] = 'Updated'
        self.repo.save_panel_message(1, saved, saved['id'], saved['revision'])
        self.assertFalse(self.repo.mark_panel_published(claim, 999))
        current = self.repo.panel_message(1, saved['id'])
        self.assertEqual(current['status'], 'publishing')
        current['channel_id'] = 11
        with self.assertRaisesRegex(RuntimeError, 'panel_recovery_required'):
            self.repo.save_panel_message(1, current, current['id'], current['revision'])

    async def test_detach_after_unknown_publication_recovers_before_deleting(self):
        with patch('ticketing.repository.time.time', return_value=1000):
            claim = self.repo.claim_panel_messages('worker', lease_seconds=1)[0]
            with patch.object(self.repo, 'mark_panel_published', side_effect=RuntimeError('database failed')):
                with self.assertRaises(RuntimeError):
                    await self.service.deliver(claim)
            self.repo.detach_panel(1, self.config['panel_ids'][0], self.config['id'])
        self.assertEqual(self.repo.panel_message(1, self.config['id'])['status'], 'delete_uncertain')
        with patch('ticketing.repository.time.time', return_value=1002):
            await self.service.deliver(self.repo.claim_panel_messages('worker')[0])
        self.assertEqual(self.port.deleted, [901])
        self.assertEqual(self.repo.panel_message(1, self.config['id'])['status'], 'detached')
