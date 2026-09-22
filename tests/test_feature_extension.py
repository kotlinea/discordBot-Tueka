"""Registration-only additions/removal through real application composition."""
from pathlib import Path
import subprocess
import sys
import unittest


class FeatureExtensionTests(unittest.TestCase):
    def test_existing_category_new_category_and_removal(self):
        root = Path(__file__).resolve().parents[1]
        before = {path: (root / path).read_bytes() for path in (
            'bot.py', 'config.py', 'dashboard/api_v1.py', 'features/registry.py',
            'features/community/registry.py', 'dashboard/frontend/src/app/Shell.tsx')}
        for mode in ('existing', 'category', 'removed'):
            with self.subTest(mode=mode):
                result = subprocess.run([sys.executable, 'tests/fixtures/g5_registration.py', mode],
                    cwd=root, capture_output=True, text=True, timeout=120)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f'{mode}:', result.stdout)
        for path, source in before.items():
            self.assertEqual((root / path).read_bytes(), source, path)
