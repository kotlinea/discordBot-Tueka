"""Config opt-in, safe writer selection, and credential-free SMTP notices."""
import json
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from deploy import backup_job as job
from deploy.compose import APPLICATIONS


class BackupJobTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = self.root / 'backup.json'
        self.options = {'version': 1, 'enabled': True,
            'environments': [{'config_dir': 'envs/prod', 'backup_root': 'backups/prod'}],
            'minimum_free_gib': 5, 'smtp': {'enabled': False}}
        self.directory = self.root / 'envs/prod'
        self.directory.mkdir(parents=True)
        self.write()
        self.metadata = {'environment': 'prod', 'project': 'tueka-prod-test'}
        self.read_metadata = self.mock('read_metadata', return_value=self.metadata)
        self.read = self.mock('read', return_value=(self.metadata, {'DISCORD_CLIENT_ID': '100'}))
        self.running = self.mock('running', return_value=set(APPLICATIONS))
        self.backup = self.mock('backup', side_effect=self.make_bundle)
        self.notify = self.mock('_notify')
        self.space = patch.object(job.shutil, 'disk_usage', return_value=SimpleNamespace(free=20 * 1024**3)).start()
        self.addCleanup(patch.stopall)

    def mock(self, name, **kwargs):
        return patch.object(job, name, **kwargs).start()

    def write(self):
        self.config.write_text(json.dumps(self.options), encoding='utf-8')
        self.config.chmod(0o600)

    def make_bundle(self, directory, destination, **kwargs):
        destination.mkdir()
        (destination / 'manifest.json').write_text('{}')
        return {}

    def smtp(self):
        return {'enabled': True, 'host': 'smtp.example.test', 'port': 465, 'tls': 'ssl',
            'username': 'PRIVATE_USERNAME', 'password': 'PRIVATE_PASSWORD',
            'from': 'backup@example.test', 'to': ['operator@example.test'],
            'on_success': False, 'timeout_seconds': 15}

    def test_disabled_ignores_unused_inputs_without_docker_writes_or_mail(self):
        self.options.update(enabled=False, environments='unused', smtp={'enabled': 'unused'})
        self.write()
        self.assertEqual(job.run(self.config), {'status': 'disabled'})
        for operation in (self.read_metadata, self.read, self.running, self.backup, self.notify):
            operation.assert_not_called()
        self.assertFalse(self.config.with_name('backup.json.lock').exists())
        self.assertFalse((self.root / 'backups').exists())

    def test_tools_rejects_ephemeral_and_read_only_backup_paths(self):
        mounts = [{'Destination': str(self.root), 'Source': '/host/project', 'Type': 'bind', 'RW': True}]
        with patch.dict(job.os.environ, {'TUEKA_DOCKER_MANAGER': '1'}), patch.object(job, 'inspect_self', return_value={'Mounts': mounts}):
            self.options['environments'][0]['backup_root'] = str(self.root.parent / 'unmounted-backup')
            self.write()
            with self.assertRaises(job.BackupConfigurationError):
                job.run(self.config)
            self.options['environments'][0]['backup_root'] = 'backups/prod'
            self.write()
            mounts.append({'Destination': str(self.root / 'backups'), 'Source': '/host/readonly', 'Type': 'bind', 'RW': False})
            with self.assertRaises(job.BackupConfigurationError):
                job.run(self.config)
        self.read_metadata.assert_not_called()
        self.backup.assert_not_called()

    def test_disabled_job_does_not_inspect_docker_even_in_tools_manager(self):
        self.options['enabled'] = False
        self.write()
        with patch.dict(job.os.environ, {'TUEKA_DOCKER_MANAGER': '1'}), patch.object(job, 'inspect_self') as inspect:
            self.assertEqual(job.run(self.config), {'status': 'disabled'})
            inspect.assert_not_called()

    def test_active_backup_uses_relative_config_paths_and_resumes_only_source(self):
        result = job.run(self.config)
        self.assertEqual(result['status'], 'backed-up')
        directory, bundle = self.backup.call_args.args
        self.assertEqual(directory, self.directory)
        self.assertEqual(bundle.parent, self.root / 'backups/prod')
        self.assertEqual(self.backup.call_args.kwargs, {'resume_source': True})
        self.assertEqual(len(result['bundles']), 1)
        self.notify.assert_not_called()
        self.assertTrue(self.config.with_name('backup.json.lock').exists())

    def test_stopped_source_is_not_started_or_read_for_credentials(self):
        self.running.return_value = set()
        self.assertEqual(job.run(self.config), {'status': 'stopped'})
        self.read.assert_not_called()
        self.backup.assert_not_called()
        self.notify.assert_not_called()
        self.assertFalse((self.root / 'backups').exists())

    def test_stopped_recovery_holds_fail_before_skip_and_notify_when_enabled(self):
        self.running.return_value = set()
        for marker in ('.recovery.lock', 'recovery-pending.json', 'recovery-fence.json'):
            for smtp_enabled in (False, True):
                with self.subTest(marker=marker, smtp_enabled=smtp_enabled):
                    self.options['smtp'] = self.smtp() if smtp_enabled else {'enabled': False}
                    self.write()
                    hold = self.directory / marker
                    hold.write_text('preserve recovery state')
                    self.notify.reset_mock()
                    with self.assertRaises(job.BackupConfigurationError):
                        job.run(self.config)
                    self.assertEqual(hold.read_text(), 'preserve recovery state')
                    self.assertEqual(self.notify.call_count, int(smtp_enabled))
                    if smtp_enabled:
                        self.assertEqual(self.notify.call_args.args[1], 'failed')
                    hold.unlink()
        self.read.assert_not_called()
        self.backup.assert_not_called()
        self.assertFalse((self.root / 'backups').exists())

    def test_stopped_held_environment_prevents_backup_of_other_active_environment(self):
        held = self.root / 'envs/stage'
        held.mkdir()
        (held / 'recovery-pending.json').write_text('{}')
        self.options['environments'].append({'config_dir': 'envs/stage', 'backup_root': 'backups/stage'})
        self.options['smtp'] = self.smtp()
        self.write()
        self.read_metadata.side_effect = lambda directory: {'environment': directory.name, 'project': 'tueka-' + directory.name + '-test'}
        self.running.side_effect = lambda directory: set(APPLICATIONS) if directory == self.directory else set()
        with self.assertRaises(job.BackupConfigurationError):
            job.run(self.config)
        self.backup.assert_not_called()
        self.notify.assert_called_once()
        self.assertEqual(self.notify.call_args.args[1], 'failed')

    def test_partial_source_hold_and_low_space_fail_before_backup(self):
        self.running.return_value = {'bot'}
        with self.assertRaises(job.BackupConfigurationError):
            job.run(self.config)
        self.running.return_value = set(APPLICATIONS)
        marker = self.directory / 'recovery-fence.json'
        marker.write_text('{}')
        with self.assertRaises(job.BackupConfigurationError):
            job.run(self.config)
        marker.unlink()
        self.space.return_value = SimpleNamespace(free=1024**3)
        with self.assertRaises(job.BackupConfigurationError):
            job.run(self.config)
        self.backup.assert_not_called()
        self.assertFalse((self.root / 'backups').exists())

    def test_duplicate_shared_application_is_rejected_before_stopping_either(self):
        stage = self.root / 'envs/stage'
        stage.mkdir()
        self.options['environments'].append({'config_dir': 'envs/stage', 'backup_root': 'backups/stage'})
        self.write()
        self.read_metadata.side_effect = lambda directory: {'environment': directory.name, 'project': 'tueka-' + directory.name + '-test'}
        with self.assertRaises(job.BackupConfigurationError):
            job.run(self.config)
        self.backup.assert_not_called()
        self.assertFalse((self.root / 'backups').exists())

    def test_distinct_applications_back_up_both_projects_sequentially(self):
        stage = self.root / 'envs/stage'
        stage.mkdir()
        self.options['environments'].append({'config_dir': 'envs/stage', 'backup_root': 'backups/stage'})
        self.write()
        self.read_metadata.side_effect = lambda directory: {'environment': directory.name, 'project': 'tueka-' + directory.name + '-test'}
        self.read.side_effect = lambda directory: ({}, {'DISCORD_CLIENT_ID': directory.name})
        result = job.run(self.config)
        self.assertEqual(len(result['bundles']), 2)
        self.assertEqual([call.args[0] for call in self.backup.call_args_list], [self.directory, stage])

    def lock_holder(self):
        child = subprocess.Popen([sys.executable, '-u', '-c',
            "import pathlib,sys; from deploy.backup_job import _job_lock; "
            "lock=_job_lock(pathlib.Path(sys.argv[1])); "
            "assert lock.__enter__(); print('locked',flush=True); sys.stdin.read()",
            str(self.config)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def cleanup():
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=10)
        self.addCleanup(cleanup)
        self.assertEqual(child.stdout.readline().strip(), 'locked')
        return child

    def test_busy_job_does_not_overlap_or_remove_someone_elses_lock(self):
        self.lock_holder()
        lock = self.config.with_name('backup.json.lock')
        inode = lock.stat().st_ino
        self.assertEqual(job.run(self.config), {'status': 'busy'})
        self.assertEqual(lock.stat().st_ino, inode)
        self.assertEqual(job.run(self.config), {'status': 'busy'})
        self.read_metadata.assert_not_called()
        self.backup.assert_not_called()

    def test_killed_holder_releases_lock_and_next_job_backs_up(self):
        child = self.lock_holder()
        lock = self.config.with_name('backup.json.lock')
        inode = lock.stat().st_ino
        child.kill()
        child.wait(timeout=10)
        self.assertTrue(lock.exists())
        self.assertEqual(job.run(self.config)['status'], 'backed-up')
        self.assertEqual(lock.stat().st_ino, inode)
        self.backup.assert_called_once()

    def test_old_residual_file_does_not_skip_backup_or_failure_notification(self):
        lock = self.config.with_name('backup.json.lock')
        lock.write_text('old interrupted job')
        self.assertEqual(job.run(self.config)['status'], 'backed-up')
        self.options['smtp'] = self.smtp()
        self.write()
        self.backup.side_effect = RuntimeError('PRIVATE_DATABASE_URL')
        with self.assertRaises(job.BackupJobError):
            job.run(self.config)
        self.assertEqual(self.notify.call_args.args[1], 'failed')
        self.backup.side_effect = self.make_bundle
        self.assertEqual(job.run(self.config)['status'], 'backed-up')

    def test_interrupted_recovery_is_not_hidden_by_residual_job_lock(self):
        self.config.with_name('backup.json.lock').write_text('interrupted job')
        (self.directory / '.recovery.lock').write_text('recovery requires inspection')
        self.options['smtp'] = self.smtp()
        self.write()
        with self.assertRaises(job.BackupConfigurationError):
            job.run(self.config)
        self.backup.assert_not_called()
        self.notify.assert_called_once()
        self.assertEqual(self.notify.call_args.args[1], 'failed')

    def test_invalid_inputs_never_invoke_backup_or_smtp(self):
        original = json.loads(json.dumps(self.options))
        invalid = [dict(original, enabled='true'), dict(original, version=True),
            dict(original, minimum_free_gib=0), dict(original, minimum_free_gib=True),
            dict(original, unknown='PRIVATE_VALUE'), dict(original, environments=[]),
            dict(original, environments=[{'config_dir': 'envs/prod', 'backup_root': 'envs/prod/dumps'}]),
            dict(original, environments=original['environments'] * 2),
            dict(original, smtp={**self.smtp(), 'tls': 'plain'}),
            dict(original, smtp={**self.smtp(), 'host': 'smtp://PRIVATE_SERVER'}),
            dict(original, smtp={**self.smtp(), 'to': ['operator@example.test\nBcc: PRIVATE_VALUE']}),
            dict(original, smtp={**self.smtp(), 'password': ''})]
        for value in invalid:
            with self.subTest(value=list(value)):
                self.options = value
                self.write()
                with self.assertRaises(job.BackupConfigurationError) as error:
                    job.run(self.config)
                self.assertNotIn('PRIVATE', str(error.exception))
        self.backup.assert_not_called()
        self.notify.assert_not_called()

    def test_malformed_json_error_does_not_echo_private_content(self):
        self.config.write_text('{"password": "PRIVATE_VALUE", invalid')
        with self.assertRaises(job.BackupConfigurationError) as error:
            job.run(self.config)
        self.assertNotIn('PRIVATE', str(error.exception))
        self.read_metadata.assert_not_called()

    def test_invalid_destination_parent_fails_before_docker_or_mail(self):
        (self.root / 'not-a-directory').write_text('preserve')
        self.options['environments'][0]['backup_root'] = 'not-a-directory/child'
        self.options['smtp'] = self.smtp()
        self.write()
        with self.assertRaises(job.BackupConfigurationError):
            job.run(self.config)
        self.read_metadata.assert_not_called()
        self.notify.assert_not_called()
        self.assertEqual((self.root / 'not-a-directory').read_text(), 'preserve')

    def test_valid_smtp_receives_preflight_failure_notice_without_stopping_writers(self):
        self.options['smtp'] = self.smtp()
        self.write()
        self.space.return_value = SimpleNamespace(free=0)
        with self.assertRaises(job.BackupConfigurationError):
            job.run(self.config)
        self.backup.assert_not_called()
        self.notify.assert_called_once()
        self.assertEqual(self.notify.call_args.args[1], 'failed')

    def test_cli_disabled_config_and_exclusive_arguments(self):
        self.options['enabled'] = False
        self.write()
        entry = Path(__file__).resolve().parents[1] / 'scripts/recovery.py'
        base = [sys.executable, str(entry), 'scheduled-backup', '--backup-config', str(self.config)]
        result = subprocess.run(base, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'status': 'disabled'})
        result = subprocess.run([*base, '--config-dir', str(self.directory)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('requires only --backup-config', result.stderr)

    def test_failure_notification_is_opt_in_and_never_contains_exception_details(self):
        self.backup.side_effect = RuntimeError('PRIVATE_DATABASE_URL')
        with self.assertRaises(job.BackupJobError) as error:
            job.run(self.config)
        self.assertNotIn('PRIVATE', str(error.exception))
        self.notify.assert_not_called()
        self.options['smtp'] = self.smtp()
        self.write()
        with self.assertRaises(job.BackupJobError):
            job.run(self.config)
        self.notify.assert_called_once()
        self.assertEqual(self.notify.call_args.args[1], 'failed')
        self.assertTrue(self.config.with_name('backup.json.lock').exists())

    def test_success_notice_is_separate_opt_in_and_failure_keeps_backup(self):
        self.options['smtp'] = self.smtp()
        self.write()
        first = job.run(self.config)
        self.notify.assert_not_called()
        self.options['smtp']['on_success'] = True
        self.write()
        self.notify.side_effect = RuntimeError('PRIVATE_SMTP_PASSWORD')
        with self.assertRaises(job.BackupJobError) as error:
            job.run(self.config)
        self.assertEqual(str(error.exception), 'Backup completed, but SMTP notification failed')
        self.assertTrue(Path(first['bundles'][0]).is_dir())
        self.assertEqual(len(list((self.root / 'backups/prod').iterdir())), 2)

    @unittest.skipUnless(job.os.name == 'posix', 'POSIX file permission contract')
    def test_smtp_requires_private_configuration_file(self):
        self.options['smtp'] = self.smtp()
        self.write()
        self.config.chmod(0o644)
        with self.assertRaises(job.BackupConfigurationError):
            job.run(self.config)
        self.backup.assert_not_called()


class SmtpNoticeTests(unittest.TestCase):
    def test_both_tls_modes_validate_certificates_and_send_no_backup_attachment(self):
        for mode in ('ssl', 'starttls'):
            with self.subTest(mode=mode), patch.object(job.smtplib, 'SMTP_SSL') as secure, patch.object(job.smtplib, 'SMTP') as start:
                options = {'host': 'smtp.example.test', 'port': 465 if mode == 'ssl' else 587,
                    'tls': mode, 'username': 'PRIVATE_USER', 'password': 'PRIVATE_PASSWORD',
                    'from': 'backup@example.test', 'to': ['operator@example.test'], 'timeout_seconds': 15}
                job._notify(options, 'failed')
                factory = secure if mode == 'ssl' else start
                unused = start if mode == 'ssl' else secure
                unused.assert_not_called()
                client = factory.return_value.__enter__.return_value
                context = factory.call_args.kwargs.get('context') if mode == 'ssl' else client.starttls.call_args.kwargs['context']
                self.assertTrue(context.check_hostname)
                self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
                client.login.assert_called_once_with('PRIVATE_USER', 'PRIVATE_PASSWORD')
                message = client.send_message.call_args.args[0]
                self.assertFalse(message.is_multipart())
                self.assertNotIn('PRIVATE', message.as_string())
                self.assertNotIn('database.dump', message.as_string())
                self.assertEqual(factory.call_args.kwargs['timeout'], 15)
