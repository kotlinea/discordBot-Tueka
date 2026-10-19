"""Backup resumption readiness and scheduled failure reporting (mocked Docker)."""
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from deploy import backup_job, compose, recovery


class BackupResumeHealthReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.destination = self.root / 'backups'
        self.options = self.root / 'backup.json'
        self.options.write_text(json.dumps({
            'version': 1, 'enabled': True,
            'environments': [{'config_dir': 'source', 'backup_root': 'backups'}],
            'smtp': {'enabled': True, 'host': 'smtp.example.test', 'tls': 'ssl',
                     'from': 'backup@example.test', 'to': ['operator@example.test'],
                     'on_success': True},
        }), encoding='utf-8')
        self.options.chmod(0o600)
        metadata = {'environment': 'stage', 'project': 'tueka-stage-health', 'image': 'image'}
        self.replace(recovery, 'read', return_value=(metadata, {'DISCORD_CLIENT_ID': '1'}))
        self.replace(recovery, 'image_id', return_value='image-id')
        self.replace(recovery.subprocess, 'check_output', return_value='image-id')
        self.replace(recovery, 'operation', return_value=b'{}')
        self.running = self.replace(recovery, 'running', return_value=set(compose.APPLICATIONS))
        self.execute = self.replace(compose, 'execute', return_value=SimpleNamespace(stdout='container'))
        self.replace(backup_job, '_validate_mounts')
        self.replace(backup_job, '_active_environments', return_value=[(self.source, self.destination)])
        self.notify = self.replace(backup_job, '_notify')

    def replace(self, target, name, **kwargs):
        replacement = patch.object(target, name, **kwargs)
        self.addCleanup(replacement.stop)
        return replacement.start()

    def test_success_waits_for_resumed_services_before_completed_notification(self):
        result = backup_job.run(self.options)
        self.assertEqual(result['status'], 'backed-up')
        self.assertEqual(self.execute.call_args.args, (
            self.source, 'up', '-d', '--no-deps', '--wait', '--wait-timeout', '120',
            *sorted(compose.APPLICATIONS)))
        self.notify.assert_called_once()
        self.assertEqual(self.notify.call_args.args[1], 'completed')

    def test_unhealthy_resume_reports_failure_but_preserves_completed_bundle(self):
        def execute(directory, *args, **kwargs):
            # Docker's detached start succeeds even when readiness later fails.
            # Only --wait makes the mocked readiness failure observable.
            if args[0] == 'up' and any(service in args for service in compose.APPLICATIONS) and '--wait' in args:
                raise subprocess.CalledProcessError(1, 'docker-compose-wait')
            return SimpleNamespace(stdout='container')
        self.execute.side_effect = execute
        with self.assertRaises(backup_job.BackupJobError):
            backup_job.run(self.options)
        bundles = list(self.destination.iterdir())
        self.assertEqual(len(bundles), 1)
        self.assertTrue((bundles[0] / 'manifest.json').is_file())
        self.assertTrue((bundles[0] / 'database.dump').is_file())
        self.assertTrue((bundles[0] / 'transcripts.tar').is_file())
        self.notify.assert_called_once()
        self.assertEqual(self.notify.call_args.args[1], 'failed')
        self.assertFalse((self.source / '.recovery.lock').exists())
        self.assertFalse((self.source / recovery.PENDING).exists())
        self.assertFalse((self.source / recovery.FENCE).exists())

    def test_previously_stopped_source_is_not_resumed(self):
        self.running.return_value = set()
        recovery.backup(self.source, self.root / 'manual-bundle', resume_source=True)
        for call in self.execute.call_args_list:
            args = call.args[1:]
            self.assertFalse(args[0] == 'up' and any(service in args for service in compose.APPLICATIONS))


if __name__ == '__main__':
    unittest.main()
