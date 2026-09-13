import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from community import CommunityRepository
from db_support import prepare_database
from guild_settings import GuildSettingsRepository


class CommunityRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = prepare_database(Path(self.temp.name) / 'test.db')
        self.repository = CommunityRepository(self.path)

    def test_parallel_xp_additions_are_not_lost_and_tracks_are_isolated(self):
        with ThreadPoolExecutor(max_workers=4) as workers:
            list(workers.map(lambda _: self.repository.add_xp(1, 10, 5), range(20)))
        self.repository.add_voice_xp(1, 10, 8)
        self.repository.add_xp(2, 10, 2)
        restarted = CommunityRepository(self.path)
        self.assertEqual(restarted.get_user(1, 10), {'xp': 100})
        self.assertEqual(restarted.get_voice_user(1, 10), {'xp': 8})
        self.assertEqual(restarted.leaderboard(2), [{'user_id': 10, 'xp': 2}])
        self.assertEqual(restarted.voice_leaderboard(2), [])

    def test_temporary_voice_tracking_and_enabled_guilds_survive_restart(self):
        self.repository.add_temporary_voice_channel(100, 1, 10)
        self.repository.add_temporary_voice_channel(200, 2, 20)
        settings = GuildSettingsRepository(self.path)
        settings.set_module(1, 'temporary_voice', enabled=True)
        settings.set_module(2, 'temporary_voice', enabled=False)
        self.assertEqual(settings.enabled_module_guild_ids('temporary_voice'), [1])
        restarted = CommunityRepository(self.path)
        restarted.remove_temporary_voice_channel(100)
        self.assertIsNone(restarted.temporary_voice_channel(100))
        self.assertEqual(restarted.temporary_voice_channel(200), {'guild_id': 2, 'owner_id': 20})
