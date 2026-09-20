"""Environment isolation and migration gating are deployment contracts."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from deploy.configuration import initialize, read, validate_promotion
from deploy.compose import up, command
from runtime.environment import load_environment

IMAGE = 'sha256:' + 'a' * 64


def configure(directory, environment, image=IMAGE, project=None):
    initialize(directory, environment, image, project)
    path = directory / 'app.env'
    content = path.read_text(encoding='utf-8')
    content = content.replace('replace-with-dedicated-bot-token', 'offline-' + environment)
    content = content.replace('replace-with-dedicated-client-id', {'dev': '1001', 'stage': '1002', 'prod': '1003'}[environment])
    content = content.replace('replace-with-dedicated-client-secret', 'offline-secret-' + environment)
    content = content.replace('.example.invalid', '.example.test')
    path.write_text(content, encoding='utf-8')


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_generation_separates_credentials_and_refuses_overwrite(self):
        for name in ('dev', 'stage', 'prod'):
            configure(self.root / name, name)
            self.assertEqual(read(self.root / name)[0]['environment'], name)
        self.assertNotEqual((self.root / 'stage/database-password').read_text(), (self.root / 'prod/database-password').read_text())
        with self.assertRaises(FileExistsError):
            initialize(self.root / 'dev', 'dev', IMAGE)

    def test_mutable_stage_image_is_rejected_before_creating_files(self):
        with self.assertRaises(ValueError):
            initialize(self.root / 'stage', 'stage', 'tueka:latest')
        self.assertFalse((self.root / 'stage').exists())

    def test_environment_project_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            initialize(self.root / 'stage', 'stage', IMAGE, 'tueka-prod')

    def test_secret_file_cannot_select_another_environment(self):
        configure(self.root / 'stage', 'stage')
        path = self.root / 'stage/app.env'
        path.write_text(path.read_text().replace('TUEKA_ENV=stage', 'TUEKA_ENV=prod'))
        with self.assertRaisesRegex(ValueError, 'different environment'):
            read(self.root / 'stage')

    def test_environment_error_names_file_field_actual_expected_and_fix(self):
        for draft in (False, True):
            directory = self.root / ('draft' if draft else 'release')
            initialize(directory, 'stage', IMAGE, draft=draft)
            path = directory / 'app.env'
            path.write_text(path.read_text().replace('TUEKA_ENV=stage', 'TUEKA_ENV=dev'))
            with self.assertRaises(ValueError) as caught:
                read(directory, draft=draft)
            message = str(caught.exception)
            for expected in (str(path), 'Field: TUEKA_ENV', 'Actual: dev', 'Expected: stage',
                             str(directory / ('setup.json' if draft else 'deployment.json')),
                             'set TUEKA_ENV=stage', '--config-dir'):
                self.assertIn(expected, message)
            self.assertNotIn((directory / 'database-password').read_text(), message)

    def test_invalid_environment_value_is_not_echoed_and_missing_file_is_named(self):
        directory = self.root / 'stage'
        initialize(directory, 'stage', IMAGE)
        path = directory / 'app.env'
        path.write_text('TUEKA_ENV=accidentally-pasted-private-value\n')
        with self.assertRaises(ValueError) as caught:
            read(directory)
        self.assertIn('Actual: <invalid value', str(caught.exception))
        self.assertNotIn('accidentally-pasted-private-value', str(caught.exception))
        path.write_text('TUEKA_ENV=\n')
        with self.assertRaisesRegex(ValueError, '<missing or empty>'):
            read(directory)
        path.unlink()
        with self.assertRaises(ValueError) as caught:
            read(directory)
        self.assertIn(str(path), str(caught.exception))
        self.assertIn('app.env is missing', str(caught.exception))

    def test_database_endpoint_and_password_are_bound_to_environment(self):
        for replacement in ('@outside:5432', '@postgres:5433', '@postgres:5432/tueka_prod'):
            directory = self.root / str(len(list(self.root.iterdir())))
            configure(directory, 'stage')
            path = directory / 'app.env'
            path.write_text(path.read_text().replace('@postgres:5432', replacement))
            with self.assertRaisesRegex(ValueError, 'Database secrets'):
                read(directory)

    def test_placeholders_and_http_production_are_rejected(self):
        initialize(self.root / 'empty', 'stage', IMAGE)
        with self.assertRaises(ValueError):
            read(self.root / 'empty')
        configure(self.root / 'prod', 'prod')
        path = self.root / 'prod/app.env'
        path.write_text(path.read_text().replace('https://', 'http://'))
        with self.assertRaises(ValueError):
            read(self.root / 'prod')

    def test_database_password_rejects_windows_carriage_return(self):
        configure(self.root / 'dev', 'dev')
        path = self.root / 'dev/database-password'
        path.write_bytes(path.read_bytes() + b'\r\n')
        with self.assertRaisesRegex(ValueError, 'Database secrets'):
            read(self.root / 'dev')

    def test_promotion_requires_same_image_and_different_secrets(self):
        stage, prod = self.root / 'stage', self.root / 'prod'
        configure(stage, 'stage')
        configure(prod, 'prod')
        validate_promotion(stage, prod)
        metadata = json.loads((prod / 'deployment.json').read_text())
        metadata['image'] = 'sha256:' + 'b' * 64
        (prod / 'deployment.json').write_text(json.dumps(metadata))
        with self.assertRaisesRegex(ValueError, 'exact Stage image'):
            validate_promotion(stage, prod)
        metadata['image'] = IMAGE
        (prod / 'deployment.json').write_text(json.dumps(metadata))
        path = prod / 'app.env'
        path.write_text(path.read_text().replace('offline-prod', 'offline-stage'))
        with self.assertRaisesRegex(ValueError, 'separate'):
            validate_promotion(stage, prod)

    def test_explicit_app_env_is_authoritative_and_does_not_expand(self):
        secret = self.root / 'secret.env'
        secret.write_text('SECRET=literal${OTHER}\nDATA_DIR=/wrong\n', encoding='utf-8-sig')
        with patch.dict(os.environ, {'TUEKA_ENV_FILE': str(secret), 'DATA_DIR': '/data'}, clear=True):
            load_environment()
            self.assertEqual(os.environ['SECRET'], 'literal${OTHER}')
            self.assertEqual(os.environ['DATA_DIR'], '/wrong')
        with patch.dict(os.environ, {'TUEKA_ENV_FILE': str(self.root / 'missing')}, clear=True):
            with self.assertRaises(RuntimeError):
                load_environment()

    def test_no_implicit_dotenv(self):
        with patch.dict(os.environ, {}, clear=True), patch('runtime.environment.load_dotenv') as load:
            load_environment()
            load.assert_not_called()

    def test_migration_failure_does_not_restart_writers(self):
        configure(self.root / 'stage', 'stage')
        commands = []

        def execute(directory, *args, **kwargs):
            commands.append(args)
            if args[0] == 'wait':
                raise RuntimeError('migration failed')

        with patch('deploy.compose.execute', side_effect=execute), patch('deploy.compose.subprocess.run'):
            with self.assertRaisesRegex(RuntimeError, 'migration failed'):
                up(self.root / 'stage')
        self.assertLess(commands.index(('stop', 'bot', 'dashboard', 'social-worker')), commands.index(('up', '-d', 'migrate')))
        self.assertEqual(commands[-1], ('wait', 'migrate'))

    def test_status_and_stop_can_select_project_with_missing_credentials(self):
        directory = self.root / 'stage'
        configure(directory, 'stage')
        (directory / 'app.env').unlink()
        args, _ = command(directory)
        self.assertIn('tueka-stage', args)
        with self.assertRaises(ValueError):
            up(directory)

    def test_missing_dev_image_does_not_stop_writers(self):
        directory = self.root / 'dev'
        configure(directory, 'dev')
        (self.root / 'dashboard/frontend').mkdir(parents=True)
        with patch('deploy.compose.ROOT', self.root), patch('deploy.compose.execute') as execute, patch('deploy.compose.subprocess.run', side_effect=RuntimeError('missing image')):
            with self.assertRaisesRegex(RuntimeError, 'missing image'):
                up(directory)
        self.assertFalse(any(item.args[1] == 'stop' for item in execute.call_args_list))

    def test_dev_prepares_nested_mountpoint_and_preserves_existing_dependencies(self):
        directory = self.root / 'dev'
        configure(directory, 'dev')
        frontend = self.root / 'dashboard/frontend'
        frontend.mkdir(parents=True)
        modules = frontend / 'node_modules'

        def execute(directory, *args, **kwargs):
            if args[0] in ('build', 'up'):
                self.assertTrue(modules.is_dir())

        with patch('deploy.compose.ROOT', self.root), patch('deploy.compose.execute', side_effect=execute), patch('deploy.compose.subprocess.run'):
            up(directory)
            marker = modules / 'existing-dependency'
            marker.write_text('preserved')
            up(directory)
            self.assertEqual(marker.read_text(), 'preserved')
