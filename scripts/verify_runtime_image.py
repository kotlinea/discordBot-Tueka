"""Exercise the production image against an isolated PostgreSQL test schema.

Requires host TUEKA_TEST_DATABASE_URL and container TUEKA_CONTAINER_DATABASE_URL.
Never starts Discord login or supplies application credentials.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit, urlunsplit
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database import connect
from database.testing import temporary_database
from database.migrations import load


def docker(*args, check=True):
    return subprocess.run(['docker', *args], check=check, text=True, capture_output=True, timeout=120)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--network', required=True)
    args = parser.parse_args()
    container_base = urlsplit(os.environ['TUEKA_CONTAINER_DATABASE_URL'])
    if not container_base.path.lstrip('/').startswith('tueka_test'):
        raise ValueError('Container connection must target a dedicated test database')
    names = []
    with temporary_database(migrate=False) as host_url:
        container_url = urlunsplit(container_base._replace(query=urlsplit(host_url).query))
        common = ['--read-only', '--security-opt', 'no-new-privileges:true', '--cap-drop', 'ALL',
                  '--tmpfs', '/tmp:rw,noexec,nosuid,size=128m',
                  '--tmpfs', '/data:rw,nosuid,uid=10001,gid=10001,size=64m',
                  '--network', args.network, '-e', 'DATABASE_URL=' + container_url,
                  '-e', 'DISCORD_TOKEN=offline-test', '-e', 'DISCORD_CLIENT_ID=1',
                  '-e', 'DISCORD_CLIENT_SECRET=offline-test', '-e', 'SESSION_SECRET=offline-test',
                  '-e', 'DISCORD_REDIRECT_URI=http://localhost/oauth/callback', '-e', 'SOCIAL_X_MODE=poll']
        try:
            assert docker('run', '--rm', *common, args.image, '--help').returncode == 0
            assert docker('run', '--rm', *common, args.image, 'unknown', check=False).returncode == 2
            for expected in (load(), []):
                result = docker('run', '--rm', *common, args.image, 'migrate')
                applied = json.loads(result.stdout)['applied']
                assert len(applied) == len(expected), result.stdout
            for command in ('dashboard', 'social-worker'):
                name = 'tueka-image-check-' + uuid.uuid4().hex
                docker('run', '-d', '--name', name, *common, args.image, command)
                names.append(name)
            dashboard, worker = names
            probe = '''import os, urllib.request, re, pathlib, shutil
assert os.getuid() == 10001
assert 'NoNewPrivs:\\t1' in open('/proc/self/status').read()
for name in ('.env', '.env.postgres-dev', '.git', '.idea', 'data', '.venv', '.venv-p013'):
    assert not pathlib.Path('/app', name).exists(), name
for executable in ('node', 'npm', 'git'):
    assert shutil.which(executable) is None, executable
assert not pathlib.Path('/app/handbook').exists()
assert not pathlib.Path('/app/goal.md').exists()
for path in ('feature_registry.py', 'guild_settings/models.py', 'social/providers.py',
             'cogs/community.py', 'cogs/engagement.py', 'cogs/welcome.py', 'cogs/tickets.py',
             'cogs/social_updates.py', 'dashboard/frontend/src/features/modules',
             'dashboard/frontend/src/features/guilds', 'dashboard/frontend/src/features/tickets',
             'dashboard/frontend/src/features/reaction-roles', 'dashboard/frontend/src/features/suggestions',
             'dashboard/frontend/src/routing/RegisteredModule.tsx'):
    assert not pathlib.Path('/app', path).exists(), path
from features.registry import REGISTRY
from features.loading import resolve_bindings
assert len([feature for feature in REGISTRY.features if feature.dashboard]) == 24
for process in ('bot', 'api', 'worker'):
    assert resolve_bindings(REGISTRY.for_process(process)), process
print('category bindings resolve; retired source paths absent: OK')
for path in ('operations/index.html', 'reference/environment.html', 'reference/architecture.html', 'reference/api.html', 'reference/extending.html', 'social/worker.html', 'EXECUTION_PLAN.html', 'PROGRESS0910.html', 'TESTING.html', 'en/operations.html'):
    assert not pathlib.Path('/opt/tueka-assets/docs', path).exists(), path
    try:
        urllib.request.urlopen('http://127.0.0.1:8000/docs/' + path)
    except urllib.error.HTTPError as error:
        assert error.code == 404, path
    else:
        raise AssertionError('Private document served: ' + path)
try:
    open('/app/forbidden-write', 'w')
except OSError:
    pass
else:
    raise AssertionError('root filesystem is writable')
for path in ('/ui/index.html', '/docs/', '/docs/en/getting-started.html', '/servers'):
    response = urllib.request.urlopen('http://127.0.0.1:8000' + path)
    assert response.status == 200
    html = response.read().decode()
    for asset in re.findall(r'(?:src|href)="([^"?#]+\\.(?:js|css))"', html):
        if asset.startswith('/'):
            assert urllib.request.urlopen('http://127.0.0.1:8000' + asset).status == 200
print('nonroot, read-only, no-new-privileges, SPA/Docs/assets: OK')
'''
            deadline = time.monotonic() + 60
            while True:
                result = docker('exec', dashboard, 'python', '-c', probe, check=False)
                if result.returncode == 0:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError(result.stderr + docker('logs', dashboard).stderr)
                time.sleep(1)
            print(result.stdout.strip())
            deadline = time.monotonic() + 30
            while True:
                with connect(host_url) as connection:
                    ready = connection.execute('SELECT COUNT(*) AS n FROM social_worker_state').fetchone()['n'] == 1
                if ready:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('Worker heartbeat missing')
                time.sleep(1)
            for name in names:
                state = json.loads(docker('inspect', name).stdout)[0]
                assert state['State']['Running']
                assert state['Config']['User'] == '10001:10001'
                assert state['HostConfig']['ReadonlyRootfs']
                docker('stop', '--time', '10', name)
                state = json.loads(docker('inspect', name).stdout)[0]['State']
                assert state['ExitCode'] == 0, state
            print('migration/reapply, worker heartbeat, process shutdown: OK')
        finally:
            for name in names:
                docker('rm', '-f', name, check=False)


if __name__ == '__main__':
    main()
