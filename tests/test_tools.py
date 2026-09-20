"""Daemon paths and client paths are different on Docker Desktop."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import tools
from deploy.docker_bridge import daemon_path, translate, literal_values, port_probe


class ToolsMountTests(unittest.TestCase):
    def test_missing_host_binding_fails_closed_and_removes_only_probe(self):
        with patch('deploy.docker_bridge.inspect_self', return_value={'Image': 'sha256:test'}), \
             patch('deploy.docker_bridge.subprocess.run') as run, \
             patch('deploy.docker_bridge.subprocess.check_output', return_value='[{"NetworkSettings":{"Ports":{"9999/tcp":[]}}}]'):
            with self.assertRaisesRegex(ValueError, 'Host port 12345 is unavailable'):
                port_probe(12345)
            self.assertEqual(run.call_args.args[0][1:3], ['rm', '-f'])
            self.assertTrue(run.call_args.args[0][-1].startswith('tueka-port-check-'))

    def test_compiled_values_are_not_interpolated_twice(self):
        self.assertEqual(literal_values({'environment': {'VALUE': 'literal${NAME}-$value'}, 'port': 42}),
                         {'environment': {'VALUE': 'literal$${NAME}-$$value'}, 'port': 42})

    def test_longest_bind_mapping_and_unicode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mounts = [{'Type': 'bind', 'Destination': str(root), 'Source': '/host_mnt/d/日本語 repo'},
                      {'Type': 'bind', 'Destination': str(root / 'external'), 'Source': '/srv/config'}]
            self.assertEqual(daemon_path(root / 'data/stage/app.env', mounts), '/host_mnt/d/日本語 repo/data/stage/app.env')
            self.assertEqual(daemon_path(root / 'external/app.env', mounts), '/srv/config/app.env')

    def test_unshared_or_volume_source_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, 'not shared'):
                daemon_path(temporary, [])
            with self.assertRaisesRegex(ValueError, 'bind mount required'):
                daemon_path(temporary, [{'Type': 'volume', 'Destination': temporary, 'Source': '/data'}])

    def test_only_engine_sources_are_translated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mounts = [{'Type': 'bind', 'Destination': str(root), 'Source': '/host/repo'}]
            model = {'services': {'web': {'build': {'context': str(root)}, 'volumes': [
                {'type': 'bind', 'source': str(root / 'dashboard'), 'target': '/app/dashboard'},
                {'type': 'volume', 'source': 'persist', 'target': '/data'}]}},
                'secrets': {'app': {'file': str(root / 'data/app.env')}},
                'configs': {'config': {'file': str(root / 'deploy/config')}}}
            result = translate(copy.deepcopy(model), mounts)
            self.assertEqual(result['services']['web']['build']['context'], str(root))
            self.assertEqual(result['services']['web']['volumes'][0]['source'], '/host/repo/dashboard')
            self.assertEqual(result['services']['web']['volumes'][1]['source'], 'persist')
            self.assertEqual(result['secrets']['app']['file'], '/host/repo/data/app.env')
            self.assertEqual(result['configs']['config']['file'], '/host/repo/deploy/config')


class ToolsFilesTests(unittest.TestCase):
    def test_stale_dependency_image_rejected_but_lock_repair_allowed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installed = root / 'installed'
            installed.mkdir()
            (installed / 'requirements.lock').write_text('old')
            (root / 'requirements.lock').write_text('new')
            with patch.object(tools, 'SOURCE', root):
                with self.assertRaisesRegex(ValueError, 'dependencies are stale'):
                    tools.check_dependencies('test-python', installed)
                tools.check_dependencies('lock-python', installed)

    def test_snapshot_excludes_host_dependencies_and_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'source'
            root.mkdir()
            (root / '.env').write_text('private')
            (root / 'app.env').write_text('private')
            (root / 'module.py').write_text('value = 1')
            for name in ('node_modules', '.venv-operator', 'data', 'artifacts', '.tools-runs'):
                (root / name).mkdir()
                (root / name / 'never-copy').write_text('private')
            target = Path(temporary) / 'copy'
            with patch.object(tools, 'SOURCE', root):
                tools.copy_source(target)
            self.assertEqual([p.name for p in target.iterdir()], ['module.py'])

    @unittest.skipUnless(hasattr(__import__('os'), 'chown'), 'POSIX ownership')
    def test_writeback_preserves_mode_and_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'new'
            target = root / 'generated'
            source.write_text('new')
            target.write_text('old')
            target.chmod(0o640)
            before = target.stat()
            with patch.object(tools, 'SOURCE', root):
                tools.writeback(source, 'generated')
            after = target.stat()
            self.assertEqual(target.read_text(), 'new')
            self.assertEqual((after.st_mode, after.st_uid, after.st_gid), (before.st_mode, before.st_uid, before.st_gid))
