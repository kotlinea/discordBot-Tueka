"""Writer startup remains exclusive through readiness and health verification."""
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from deploy import recovery, setup


class SetupWriterFencingTests(unittest.TestCase):
    def test_first_start_checks_ports_and_releases_lock_after_health_success_or_failure(self):
        for fail_health in (False, True):
            with self.subTest(fail_health=fail_health), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                calls = []
                def port_check(metadata):
                    self.assertTrue((directory / '.recovery.lock').exists())
                def start_writers(*args):
                    self.assertTrue((directory / '.recovery.lock').exists())
                def execute(directory, *args, **kwargs):
                    calls.append(args[0])
                    self.assertTrue((Path(directory) / '.recovery.lock').exists())
                    if args[0] == 'run' and fail_health:
                        raise OSError('synthetic health failure')
                    return SimpleNamespace(stdout='')
                with patch.object(setup, 'read', return_value=({}, {})), \
                     patch.object(setup, 'check_ports', side_effect=port_check) as ports, \
                     patch.object(setup.compose, '_up', side_effect=start_writers) as up, \
                     patch.object(setup.compose, 'execute', side_effect=execute):
                    if fail_health:
                        with self.assertRaisesRegex(OSError, 'synthetic health failure'):
                            setup.start(directory)
                    else:
                        setup.start(directory)
                ports.assert_called_once_with({})
                up.assert_called_once_with(directory, None)
                self.assertEqual(calls, ['ps', 'up', 'run'])
                self.assertEqual(list(directory.iterdir()), [])

    def test_restore_cannot_fence_source_during_start_readiness(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, target, bundle = [root / name for name in ('source', 'target', 'bundle')]
            for directory in (source, target, bundle):
                directory.mkdir()
            for name in recovery.ARTIFACTS:
                (bundle / name).write_bytes(b'synthetic')
            configs = {source: {'project': 'tueka-stage-source'}, target: {'project': 'tueka-stage-target'}}
            states = {source: True, target: False}
            readiness_started, restore_finished = threading.Event(), threading.Event()
            errors = []
            def read(directory, **kwargs):
                return configs[Path(directory)], {'DISCORD_CLIENT_ID': '100'}
            def restore_thread():
                try:
                    if not readiness_started.wait(10):
                        raise AssertionError('readiness did not start')
                    recovery.restore(target, bundle, source_directory=source)
                except BaseException as error:
                    errors.append(error)
                finally:
                    restore_finished.set()
            def execute(directory, *args, **kwargs):
                directory = Path(directory)
                if args[:1] == ('ps',):
                    return SimpleNamespace(stdout='existing-container')
                if args[:1] == ('stop',):
                    states[directory] = False
                if args[:1] == ('up',) and 'bot' in args:
                    readiness_started.set()
                    self.assertTrue(restore_finished.wait(10))
                    self.assertFalse((source / recovery.FENCE).exists(), 'readiness must not restart a fenced source')
                    self.assertTrue((source / '.recovery.lock').exists(), 'readiness must share the startup lock')
                    states[directory] = True
                if args[:1] == ('run',) and 'snapshot' in args:
                    self.assertTrue((source / '.recovery.lock').exists(), 'health must share the startup lock')
                return SimpleNamespace(stdout='{}')
            manifest = {'source_project': configs[source]['project'], 'observations': {'migrations': [], 'queues': {}}}
            with patch.object(setup, 'read', side_effect=read), patch.object(recovery, 'read', side_effect=read), \
                 patch.object(recovery, 'load_bundle', return_value=manifest), patch.object(recovery, 'validate_target'), \
                 patch.object(recovery, 'running', side_effect=lambda directory: {'bot'} if states[Path(directory)] else set()), \
                 patch.object(recovery, 'operation', return_value=json.dumps({'migrations': [], 'queues': {}})), \
                 patch.object(setup.compose, 'execute', side_effect=execute), patch.object(setup.compose, '_up'):
                thread = threading.Thread(target=restore_thread)
                thread.start()
                try:
                    setup.start(source)
                finally:
                    readiness_started.set()
                    thread.join(10)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], ValueError)
            self.assertIn('Operation lock already exists', str(errors[0]))
            self.assertTrue(states[source])
            self.assertFalse((source / recovery.FENCE).exists())
            self.assertFalse((source / '.recovery.lock').exists())
            self.assertEqual(json.loads((target / recovery.PENDING).read_text())['status'], 'restoring')

    def test_start_keeps_existing_recovery_holds_and_never_starts_writers(self):
        for marker in (recovery.PENDING, recovery.FENCE):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                hold = directory / marker
                hold.write_text('preserve recovery hold')
                with patch.object(setup, 'read', return_value=({}, {})), patch.object(setup.compose, 'execute') as execute:
                    execute.return_value.stdout = 'existing-container'
                    with self.assertRaisesRegex(ValueError, 'Recovery'):
                        setup.start(directory)
                self.assertEqual(hold.read_text(), 'preserve recovery hold')
                self.assertFalse((directory / '.recovery.lock').exists())
                self.assertEqual([call.args[1] for call in execute.call_args_list], ['ps'])
