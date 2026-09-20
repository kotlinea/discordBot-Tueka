"""First install from empty private configuration, with an offline Discord fixture."""
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts'), str(ROOT / 'tests')]
from deploy import compose, setup
from verify_compose import free_port, ready, docker


def main():
    (ROOT / '.tools-runs').mkdir(exist_ok=True)
    unique = uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix='setup-', dir=ROOT / '.tools-runs') as temporary:
        root = Path(temporary)
        directory = root / 'stage'
        setup.check(directory)
        setup.configure(directory, 'stage', 'tueka-stage-setup-' + unique)
        assert not (directory / 'deployment.json').exists()
        path = directory / 'app.env'
        content = path.read_text().replace('replace-with-dedicated-bot-token', 'offline-stage')
        content = content.replace('replace-with-dedicated-client-id', '1002').replace('replace-with-dedicated-client-secret', 'offline-secret')
        path.write_text(content.replace('.example.invalid', '.example.test'))
        draft = json.loads((directory / 'setup.json').read_text())
        draft['dashboard_port'] = free_port()
        (directory / 'setup.json').write_text(json.dumps(draft))
        setup.check(directory)
        preserved = {name: (directory / name).read_bytes() for name in ('app.env', 'database-password', 'postgres-admin-password')}
        offline = root / 'offline.json'
        offline.write_text(json.dumps({'services': {'bot': {
            'entrypoint': ['python', '-c', "exec(open('tests/fixtures/offline_bot.py').read())"],
            'command': [], 'restart': 'no'}}}))
        original = compose.command
        def command(directory):
            base, env = original(directory)
            return [*base, '-f', str(offline)], env
        with patch('deploy.compose.command', side_effect=command):
            try:
                metadata = setup.build(directory)
                # Exercise additive upgrades on an already image-pinned deployment.
                original_env = path.read_bytes()
                legacy = b''.join(line for line in original_env.splitlines(keepends=True)
                                  if not line.startswith(b'HEARTBEAT_MAX_AGE_SECONDS='))
                assert legacy != original_env
                path.write_bytes(legacy)
                setup.configure(directory, 'stage')
                assert path.read_bytes().startswith(legacy)
                assert b'HEARTBEAT_MAX_AGE_SECONDS=30' in path.read_bytes().splitlines()
                preserved['app.env'] = path.read_bytes()
                setup.configure(directory, 'stage')
                assert setup.build(directory) == metadata
                setup.start(directory)
                ready(directory)
                assert all((directory / name).read_bytes() == value for name, value in preserved.items())
                print('setup: draft, configure/build retry, immutable image, migration, offline startup and secrets preserved: OK', flush=True)
            finally:
                if (directory / 'deployment.json').exists():
                    assert json.loads((directory / 'deployment.json').read_text())['project'] == 'tueka-stage-setup-' + unique
                    compose.execute(directory, 'down', '-v', '--remove-orphans')
                docker('image', 'rm', 'tueka-stage-setup-' + unique + ':setup', check=False)


if __name__ == '__main__':
    main()
