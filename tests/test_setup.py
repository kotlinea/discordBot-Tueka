"""First-install safety: drafts, credentials, failure and idempotent retries."""
import json
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from deploy import setup
from deploy.configuration import read_metadata
from deploy import env_template


class SetupTests(unittest.TestCase):
    def test_configure_accepts_an_existing_empty_directory(self):
        self.directory.mkdir()
        setup.configure(self.directory, 'dev')
        self.assertTrue((self.directory / 'setup.json').is_file())
        self.assertFalse((self.directory / '.recovery.lock').exists())

    def test_configure_preserves_an_existing_operation_lock(self):
        self.directory.mkdir()
        lock = self.directory / '.recovery.lock'
        lock.write_text('active operation')
        with self.assertRaisesRegex(ValueError, 'Operation lock already exists') as caught:
            setup.configure(self.directory, 'dev')
        self.assertIn(str(lock), str(caught.exception))
        self.assertEqual(lock.read_text(), 'active operation')
        self.assertEqual(list(self.directory.iterdir()), [lock])

    def test_configure_preserves_partial_secrets(self):
        self.directory.mkdir()
        secret = self.directory / 'database-password'
        secret.write_text('private-value')
        with self.assertRaisesRegex(ValueError, 'Incomplete configuration') as caught:
            setup.configure(self.directory, 'dev')
        self.assertNotIn('private-value', str(caught.exception))
        self.assertEqual(secret.read_text(), 'private-value')
        self.assertFalse((self.directory / '.recovery.lock').exists())

    def test_configure_reports_a_file_at_the_directory_path(self):
        self.directory.write_text('keep')
        with self.assertRaisesRegex(ValueError, 'Configuration path must be a directory'):
            setup.configure(self.directory, 'dev')
        self.assertEqual(self.directory.read_text(), 'keep')

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

    def test_all_settings_generated_for_each_environment(self):
        keys = env_template.parse(env_template.TEMPLATE.read_text(encoding='utf-8'), env_template.TEMPLATE)
        for environment in ('dev', 'stage', 'prod'):
            directory = self.directory / environment
            setup.configure(directory, environment)
            values = env_template.parse((directory / 'app.env').read_text(), directory / 'app.env')
            self.assertEqual(set(values), set(keys))
            self.assertEqual(values['TUEKA_ENV'], environment)
            self.assertEqual(values['TICKET_ENCRYPTION_KEY'], '')
            self.assertEqual(values['GEMINI_API_KEY'], '')
            self.assertEqual(values['DASHBOARD_HTTPS_ONLY'], 'false' if environment == 'dev' else 'true')
            self.assertTrue(values['SESSION_SECRET'])
            self.assertTrue(values['MONITORING_TOKEN'])

    def test_existing_file_is_only_extended_preserving_bom_comments_empty_and_custom_values(self):
        setup.configure(self.directory, 'dev')
        path = self.directory / 'app.env'
        # Simulate an older file with missing fields, quotes, CRLF and no final newline.
        text = path.read_text(encoding='utf-8')
        removed = ('GEMINI_MODEL=', 'HEARTBEAT_MAX_AGE_SECONDS=', 'MONITORING_TOKEN=', 'DATABASE_URL=')
        text = '\r\n'.join(line for line in text.splitlines() if not line.startswith(removed))
        text += '\r\n# Keep custom text\r\nCUSTOM_KEY="literal${VALUE}"'
        original = b'\xef\xbb\xbf' + text.encode('utf-8')
        path.write_bytes(original)
        siblings = {p.name: p.read_bytes() for p in self.directory.iterdir() if p != path}
        setup.configure(self.directory, 'dev')
        after = path.read_bytes()
        self.assertTrue(after.startswith(original))
        self.assertEqual(siblings, {p.name: p.read_bytes() for p in self.directory.iterdir() if p != path})
        values = env_template.parse(after.decode('utf-8-sig'), path)
        self.assertEqual(values['CUSTOM_KEY'], 'literal${VALUE}')
        self.assertEqual(values['GEMINI_API_KEY'], '')
        self.assertEqual(values['MONITORING_TOKEN'], '')  # Never silently issue replacement credentials.
        self.assertEqual(values['HEARTBEAT_MAX_AGE_SECONDS'], '30')
        self.assertIn((self.directory / 'database-password').read_text(), values['DATABASE_URL'])
        setup.configure(self.directory, 'dev')
        self.assertEqual(after, path.read_bytes())

    def test_malformed_duplicate_or_wrong_environment_files_are_not_modified(self):
        setup.configure(self.directory, 'stage')
        path = self.directory / 'app.env'
        original = path.read_bytes()
        for suffix in (b'\nGEMINI_API_KEY=duplicate\n', b'\nUNFINISHED="broken\n'):
            before = original + suffix
            path.write_bytes(before)
            with self.assertRaises(ValueError):
                setup.configure(self.directory, 'stage')
            self.assertEqual(path.read_bytes(), before)
        path.write_bytes(original)
        with self.assertRaises(ValueError):
            setup.configure(self.directory, 'prod')
        self.assertEqual(path.read_bytes(), original)

    def test_deployed_configuration_gets_missing_keys_without_rotating_secrets(self):
        self.prepared()
        with patch('deploy.setup.subprocess.run'), patch('deploy.setup.image_id', return_value='sha256:' + 'a' * 64):
            setup.build(self.directory)
        path = self.directory / 'app.env'
        text = path.read_text()
        path.write_text('\n'.join(line for line in text.splitlines() if not line.startswith(('SESSION_SECRET=', 'TUEKA_ENV='))) + '\n')
        preserved = {p.name: p.read_bytes() for p in self.directory.iterdir() if p != path}
        setup.configure(self.directory, 'stage')
        values = env_template.parse(path.read_text(), path)
        self.assertEqual(values['SESSION_SECRET'], '')
        self.assertEqual(values['TUEKA_ENV'], 'stage')
        self.assertEqual(preserved, {p.name: p.read_bytes() for p in self.directory.iterdir() if p != path})

    def test_failed_write_keeps_original_file(self):
        setup.configure(self.directory, 'stage')
        path = self.directory / 'app.env'
        before = path.read_bytes()
        with patch('deploy.env_template.tempfile.NamedTemporaryFile', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                env_template.append_missing(path, before, 'NEW_KEY=\n')
        self.assertEqual(before, path.read_bytes())

    def test_build_cli_prints_actionable_environment_mismatch_without_building(self):
        from scripts.setup import main
        setup.configure(self.directory, 'stage')
        path = self.directory / 'app.env'
        path.write_text(path.read_text().replace('TUEKA_ENV=stage', 'TUEKA_ENV=dev'))
        output = io.StringIO()
        with patch('sys.argv', ['setup.py', 'build', '--config-dir', str(self.directory)]), \
                patch('deploy.setup.check'), patch('deploy.setup.subprocess.run') as run, \
                patch('sys.stderr', output):
            with self.assertRaises(SystemExit) as caught:
                main()
        self.assertEqual(caught.exception.code, 2)
        run.assert_not_called()
        for expected in (str(path), 'Actual: dev', 'Expected: stage', 'set TUEKA_ENV=stage'):
            self.assertIn(expected, output.getvalue())

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
