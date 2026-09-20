import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deploy.caddy import generate, render
from deploy.configuration import initialize


class CaddyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stage = self.config('stage')
        self.prod = self.config('prod')

    def config(self, environment):
        path = self.root / environment
        initialize(path, environment, 'sha256:' + 'a' * 64)
        file = path / 'app.env'
        file.write_text(file.read_text().replace('.example.invalid', '.example.com'))
        return path

    def edit(self, key, value):
        path = self.stage / 'app.env'
        lines = path.read_text().splitlines()
        path.write_text('\n'.join(value if line.startswith(key + '=') else line for line in lines) + '\n')

    def test_separate_sites_loopback_internal_block_and_no_secrets(self):
        text = render([self.stage, self.prod])
        for expected in ('stage.example.com {', 'prod.example.com {', '127.0.0.1:8001', '127.0.0.1:8000',
                         '@internal path /internal /internal/*', 'respond 404'):
            self.assertIn(expected, text)
        for directory in (self.stage, self.prod):
            self.assertNotIn((directory / 'database-password').read_text(), text)
        self.assertNotIn('log {', text)
        self.assertNotIn('SESSION_SECRET', text)

    def test_invalid_origins_and_callback_identify_file_and_field(self):
        for value in ('', 'http://stage.example.com', 'https://127.0.0.1', 'https://[::1]',
                      'https://*.example.com', 'https://example.com:8443', 'https://example.com/private',
                      'https://user:private@example.com', 'https://@example.com', 'https://example.com:', 'https://example.com?token=private',
                      'https://example.com#x', 'https://example.invalid', 'https://example.com/{bad}'):
            with self.subTest(value=value):
                self.edit('DASHBOARD_BASE_URL', 'DASHBOARD_BASE_URL=' + value)
                with self.assertRaises(ValueError) as error:
                    render([self.stage])
                self.assertIn(str(self.stage / 'app.env'), str(error.exception))
                self.assertIn('DASHBOARD_BASE_URL', str(error.exception))
                self.assertNotIn('private', str(error.exception))
        self.edit('DASHBOARD_BASE_URL', 'DASHBOARD_BASE_URL=https://stage.example.com')
        self.edit('DISCORD_REDIRECT_URI', 'DISCORD_REDIRECT_URI=https://wrong.example.com/oauth/callback')
        with self.assertRaisesRegex(ValueError, 'DISCORD_REDIRECT_URI'):
            render([self.stage])

    def test_standard_explicit_port_is_normalized_and_secure_cookies_required(self):
        self.edit('DASHBOARD_BASE_URL', 'DASHBOARD_BASE_URL=https://STAGE.example.com:443/')
        self.edit('DISCORD_REDIRECT_URI', 'DISCORD_REDIRECT_URI=https://STAGE.example.com:443/oauth/callback')
        self.assertIn('stage.example.com {', render([self.stage]))
        self.edit('DASHBOARD_HTTPS_ONLY', 'DASHBOARD_HTTPS_ONLY=false')
        with self.assertRaisesRegex(ValueError, 'DASHBOARD_HTTPS_ONLY=true'):
            render([self.stage])

    def test_invalid_configuration_does_not_create_or_overwrite_output(self):
        output = self.root / 'sites.caddy'
        output.write_text('existing host sites')
        self.edit('DASHBOARD_BASE_URL', 'DASHBOARD_BASE_URL=')
        with self.assertRaises(ValueError):
            generate([self.stage], output, overwrite=True)
        self.assertEqual(output.read_text(), 'existing host sites')
        with self.assertRaises(ValueError):
            generate([self.stage], self.root / 'new/sites.caddy')
        self.assertFalse((self.root / 'new').exists())

    def test_dev_duplicate_domain_and_environment_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'stage or prod'):
            render([self.config('dev')])
        with self.assertRaisesRegex(ValueError, 'duplicate environment'):
            render([self.stage, self.stage])
        file = self.prod / 'app.env'
        file.write_text(file.read_text().replace('prod.example.com', 'stage.example.com'))
        with self.assertRaisesRegex(ValueError, 'duplicate DASHBOARD_BASE_URL'):
            render([self.stage, self.prod])

    def test_output_requires_explicit_overwrite_and_never_targets_inputs(self):
        output = self.root / 'sites.caddy'
        generate([self.stage], output)
        before = output.read_bytes()
        with self.assertRaisesRegex(ValueError, '--overwrite'):
            generate([self.prod], output)
        self.assertEqual(before, output.read_bytes())
        generate([self.prod], output, overwrite=True)
        self.assertIn('prod.example.com', output.read_text())
        with self.assertRaisesRegex(ValueError, 'outside'):
            generate([self.stage], self.stage / 'app.env', overwrite=True)

    def test_cli_generates_combined_file_and_old_actions_reject_multiple_configs(self):
        from scripts.deploy import main
        output = self.root / 'combined.caddy'
        args = ['deploy.py', 'caddy-config', '--config-dir', str(self.stage), '--config-dir', str(self.prod), '--output', str(output)]
        with patch('sys.argv', args), patch('sys.stdout', io.StringIO()):
            main()
        self.assertIn('stage.example.com', output.read_text())
        with patch('sys.argv', ['deploy.py', 'status', '--config-dir', str(self.stage), '--config-dir', str(self.prod)]), patch('sys.stderr', io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main()
        self.assertEqual(error.exception.code, 2)
