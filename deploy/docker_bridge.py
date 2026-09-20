"""Translate client paths for sibling containers on the local Docker daemon.

Only bind/secret/config sources are daemon paths. Build contexts remain client paths.
Never log rendered Compose configuration (it may contain environment secrets).
"""
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import uuid

REAL_DOCKER = '/usr/local/libexec/docker-real'


def inspect_self():
    return json.loads(subprocess.check_output(
        [REAL_DOCKER, 'inspect', os.environ['HOSTNAME']], text=True))[0]


def daemon_path(path, mounts):
    path = Path(path).resolve()
    for mount in sorted(mounts, key=lambda item: len(item['Destination']), reverse=True):
        destination = Path(mount['Destination']).resolve()
        if path.is_relative_to(destination):
            if mount['Type'] != 'bind':
                raise ValueError(f'{path}: bind mount required for sibling container access')
            return str(PurePosixPath(mount['Source']) / path.relative_to(destination).as_posix())
    raise ValueError(f'{path}: not shared with Docker. Place it under the repository or add an explicit bind mount.')


def translate(config, mounts):
    for service in config.get('services', {}).values():
        for volume in service.get('volumes', []):
            if volume.get('type') == 'bind':
                volume['source'] = daemon_path(volume['source'], mounts)
    for kind in ('secrets', 'configs'):
        for entry in config.get(kind, {}).values():
            if 'file' in entry:
                entry['file'] = daemon_path(entry['file'], mounts)
    return config


def literal_values(value):
    """The rendered model must not undergo environment interpolation twice."""
    if isinstance(value, str):
        return value.replace('$', '$$')
    if isinstance(value, list):
        return [literal_values(item) for item in value]
    if isinstance(value, dict):
        return {key: literal_values(item) for key, item in value.items()}
    return value


def main(args):
    if not args or args[0] != 'compose':
        return subprocess.call([REAL_DOCKER, *args])
    # All callers use these global options before the subcommand.
    options, index = [], 1
    paired = {'-f', '--file', '-p', '--project-name', '--project-directory', '--env-file', '--profile', '--ansi', '--progress'}
    while index < len(args) and args[index] in paired:
        options.extend(args[index:index + 2])
        index += 2
    action = args[index:]
    if not action or action[0] in ('version', 'config'):
        return subprocess.call([REAL_DOCKER, *args])
    rendered = subprocess.run([REAL_DOCKER, 'compose', *options, '--profile', '*', 'config', '--format', 'json'],
                              capture_output=True, text=True)
    if rendered.returncode:
        # Compose errors may contain substituted secrets; do not echo its output.
        files = [options[i + 1] for i, value in enumerate(options[:-1]) if value in ('-f', '--file')]
        raise ValueError(f"Compose configuration is invalid in {', '.join(files)}. Check YAML syntax and required interpolation variables; run deploy check for the selected config directory.")
    config = translate(json.loads(rendered.stdout), inspect_self()['Mounts'])
    # Compose validates file secrets on the client even when their final sources
    # are daemon paths; use bind mounts instead of file secrets in this transient model.
    for service in config.get('services', {}).values():
        for secret in service.pop('secrets', []):
            entry = config.get('secrets', {}).get(secret['source'], {})
            if 'file' not in entry:
                raise ValueError('Tools support file secrets only')
            target = secret.get('target', secret['source'])
            if not target.startswith('/'):
                target = '/run/secrets/' + target
            service.setdefault('volumes', []).append({'type': 'bind', 'source': entry['file'],
                'target': target, 'read_only': True, 'bind': {'create_host_path': False}})
    config.pop('secrets', None)
    with tempfile.TemporaryDirectory(prefix='tueka-compose-') as scratch:
        path = Path(scratch) / 'compose.json'
        path.write_text(json.dumps(literal_values(config)), encoding='utf-8')
        path.chmod(0o600)
        return subprocess.call([REAL_DOCKER, 'compose', '-f', str(path), *action])


def port_probe(port=0):
    """Reserve briefly on the daemon, not in the tools container's namespace."""
    image = inspect_self()['Image']
    name = 'tueka-port-check-' + uuid.uuid4().hex
    try:
        subprocess.run([REAL_DOCKER, 'run', '-d', '--rm', '--name', name,
            '-p', f'127.0.0.1:{port}:9999', '--entrypoint', 'python', image,
            '-c', 'import time; time.sleep(60)'], check=True, stdout=subprocess.DEVNULL)
        state = json.loads(subprocess.check_output([REAL_DOCKER, 'inspect', name], text=True))[0]
        bindings = state['NetworkSettings']['Ports'].get('9999/tcp') or []
        # Docker Desktop can return success but no published binding on conflict.
        if not bindings or (port and int(bindings[0]['HostPort']) != port):
            raise ValueError(f'Host port {port} is unavailable; Docker did not publish the requested binding. Change dashboard_port/vite_port in the selected deployment.json or setup.json, or stop its owner.')
        return int(bindings[0]['HostPort'])
    finally:
        subprocess.run([REAL_DOCKER, 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
