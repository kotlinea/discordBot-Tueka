"""Check non-root Host ownership on a clean Linux filesystem using Docker only.

The volume and all containers are uniquely owned by this acceptance run. This is
Linux filesystem coverage, not evidence of a separate physical Linux Host run.
"""
import json
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deploy.docker_bridge import REAL_DOCKER, daemon_path, inspect_self


def main():
    state = inspect_self()
    image = state['Image']
    source = daemon_path('/workspace', state['Mounts'])
    volume = 'tueka-tools-ownership-' + uuid.uuid4().hex
    def docker(*args):
        return subprocess.check_output([REAL_DOCKER, *args], text=True).strip()
    docker('volume', 'create', '--label', 'com.tueka.tools.acceptance=ownership', volume)
    try:
        docker('run', '--rm', '-v', source + ':/source:ro', '-v', volume + ':/target', '--entrypoint', 'python', image, '-c', '''
import os, sys
from pathlib import Path
sys.path.insert(0, '/opt')
import tools
tools.SOURCE = Path('/source')
tools.copy_source(Path('/target'))
for path in [Path('/target'), *Path('/target').rglob('*')]:
    os.chown(path, 1001, 1001)
''')
        host = json.loads(docker('volume', 'inspect', volume))[0]['Mountpoint']
        common = ['run', '--rm', '-v', host + ':/workspace', '-v', '/var/run/docker.sock:/var/run/docker.sock']
        arguments = ['setup', 'configure', '--environment', 'stage', '--config-dir', 'data/environments/stage']
        print(docker(*common, image, *arguments))
        docker(*common, '--entrypoint', 'python', image, '-c', '''
import hashlib,json
from pathlib import Path
directory = Path('data/environments/stage')
assert all((p.stat().st_uid,p.stat().st_gid)==(1001,1001) for p in [directory.parent.parent,directory.parent,directory,*directory.iterdir()])
names = ('database-password','postgres-admin-password')
Path('/workspace/before.json').write_text(json.dumps({name:hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in names}))
path = directory/'app.env'
original = path.read_bytes()
path.write_bytes(b''.join(line for line in original.splitlines(keepends=True) if not line.startswith(b'HEARTBEAT_MAX_AGE_SECONDS=')))
Path('/workspace/before.env').write_bytes(path.read_bytes())
''')
        print(docker(*common, image, *arguments))
        docker(*common, '--entrypoint', 'python', image, '-c', '''
import hashlib,json
from pathlib import Path
directory = Path('data/environments/stage')
for name,digest in json.loads(Path('/workspace/before.json').read_text()).items():
    assert hashlib.sha256((directory/name).read_bytes()).hexdigest()==digest
path = directory/'app.env'
assert path.read_bytes().startswith(Path('/workspace/before.env').read_bytes())
assert b'HEARTBEAT_MAX_AGE_SECONDS=30' in path.read_bytes()
assert path.stat().st_uid==1001 and path.stat().st_gid==1001
assert directory.stat().st_mode & 0o777 == 0o700
''')
        blocker = 'tueka-tools-port-' + uuid.uuid4().hex
        try:
            docker('run', '-d', '--rm', '--name', blocker, '-p', '127.0.0.1::9999', '--entrypoint',
                   'python', image, '-c', 'import time; time.sleep(120)')
            port = json.loads(docker('inspect', blocker))[0]['NetworkSettings']['Ports']['9999/tcp'][0]['HostPort']
            docker(*common, '--entrypoint', 'python', image, '-c', '''
import json,sys
from pathlib import Path
path=Path('data/environments/stage/setup.json')
data=json.loads(path.read_text()); data['dashboard_port']=int(sys.argv[1]); path.write_text(json.dumps(data))
''', port)
            result = subprocess.run([REAL_DOCKER, *common, image, 'setup', 'check', '--config-dir',
                                     'data/environments/stage'], capture_output=True, text=True)
            assert result.returncode == 2 and f'Host port {port} is unavailable' in result.stdout, (
                f'Host port conflict was not rejected: exit={result.returncode}\n{result.stdout[-1500:]}\n{result.stderr[-1500:]}')
            assert json.loads(docker('inspect', blocker))[0]['State']['Running'], 'Existing listener was stopped'
        finally:
            subprocess.run([REAL_DOCKER, 'rm', '-f', blocker], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print('Linux filesystem: clean configure, additive retry, non-root ownership, directory privacy and keys preserved: OK')
        print('Host port conflict: rejected without stopping the existing listener: OK')
    finally:
        docker('volume', 'rm', volume)


if __name__ == '__main__':
    main()
