"""First-install safety: drafts, credentials, failure and idempotent retries."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from deploy import setup
from deploy.configuration import read_metadata


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'config'

    def prepared(self, environment='stage'):
        setup.configure(self.directory, environment)
        path = self.directory / 'app.env'
        text = path.read_text().replace('replace-with-dedicated-bot-token', 'offline-test')
        text = text.replace('replace-with-dedicated-client-id', '1').replace('replace-with-dedicated-client-secret', 'offline-secret')
        path.write_text(text.replace('.example.invalid', '.example.test'))

    def test_configure_is_a_nonstartable_draft_and_keeps_existing_secrets(self):
        setup.configure(self.directory, 'stage')
        before = {p.name: p.read_bytes() for p in self.directory.iterdir()}
        setup.configure(self.directory, 'stage')
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.directory.iterdir()})
        with self.assertRaises(FileNotFoundError):
            read_metadata(self.directory)
        with self.assertRaises(ValueError):
            setup.configure(self.directory, 'prod')

    def test_missing_credentials_prevent_build(self):
        setup.configure(self.directory, 'stage')
        with patch('deploy.setup.subprocess.run') as run:
            with self.assertRaises(ValueError):
                setup.build(self.directory)
            run.assert_not_called()

    def test_failed_build_leaves_draft_and_success_is_idempotent(self):
        self.prepared()
        before = (self.directory / 'app.env').read_bytes()
        with patch('deploy.setup.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'docker')):
            with self.assertRaises(subprocess.CalledProcessError):
                setup.build(self.directory)
        self.assertFalse((self.directory / 'deployment.json').exists())
        with patch('deploy.setup.subprocess.run') as run, patch('deploy.setup.image_id', return_value='sha256:' + 'a' * 64):
            setup.build(self.directory)
            setup.build(self.directory)
            self.assertEqual(run.call_count, 1)
        self.assertEqual(before, (self.directory / 'app.env').read_bytes())

    def test_production_cannot_build_without_stage(self):
        self.prepared('prod')
        with patch('deploy.setup.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'Stage'):
                setup.build(self.directory)
            run.assert_not_called()

    def test_migration_failure_never_runs_health_or_another_up(self):
        self.prepared()
        with patch('deploy.setup.subprocess.run'), patch('deploy.setup.image_id', return_value='sha256:' + 'a' * 64):
            setup.build(self.directory)
        with patch('deploy.setup.compose.execute') as execute, patch('deploy.setup.compose.up', side_effect=subprocess.CalledProcessError(1, 'migrate')):
            execute.return_value.stdout = 'existing-container'
            with self.assertRaises(subprocess.CalledProcessError):
                setup.start(self.directory)
            self.assertEqual(execute.call_count, 1)

    def test_missing_tools_and_non_linux_daemon_are_rejected(self):
        with patch('deploy.setup.shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'git'):
                setup.check()

        with patch('deploy.setup.shutil.which', return_value='tool'), patch('deploy.setup.subprocess.run'), patch('deploy.setup.subprocess.check_output', return_value='windows\n'):
            with self.assertRaisesRegex(ValueError, 'Linux'):
                setup.check()

    def test_port_conflicts_report_the_configured_port(self):
        with patch('deploy.setup.socket.socket') as socket:
            socket.return_value.__enter__.return_value.bind.side_effect = OSError('occupied')
            with self.assertRaisesRegex(ValueError, '8001 is unavailable'):
                setup.check_ports({'environment': 'stage', 'dashboard_port': 8001})
        with self.assertRaisesRegex(ValueError, 'must differ'):
            setup.check_ports({'environment': 'dev', 'dashboard_port': 8002, 'vite_port': 8002})
