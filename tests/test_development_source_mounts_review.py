"""Development uses current source for every distributed business package."""
from pathlib import Path
import unittest

import yaml


class DevelopmentSourceMountsTests(unittest.TestCase):
    def test_business_packages_share_current_source_with_cogs_and_api(self):
        root = Path(__file__).resolve().parents[1]
        configuration = yaml.safe_load((root / 'deploy/compose.dev.yaml').read_text())
        packages = ('applications', 'appeals', 'scheduling', 'giveaways', 'insights', 'starboard')
        for service in ('migrate', 'bot', 'dashboard', 'social-worker'):
            mounts = configuration['services'][service]['volumes']
            for package in packages:
                with self.subTest(service=service, package=package):
                    self.assertIn(f'./{package}:/app/{package}:ro', mounts)
