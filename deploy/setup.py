"""Resumable first installation; delegates all database operations to Compose."""
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys

from . import compose
from .configuration import initialize, read, read_metadata, validate_values
from . import env_template
from .locking import locked
from .recovery import image_id, write_json


def check(directory=None, *, validate_config=True):
    if sys.version_info[:2] != (3, 13):
        raise ValueError('Python 3.13 is required; see handbook/operator/setup.md')
    for name in ('git', 'docker'):
        if not shutil.which(name):
            raise ValueError(f'{name} is missing; see handbook/operator/setup.md')
    subprocess.run(['git', '--version'], check=True, capture_output=True)
    subprocess.run(['docker', 'compose', 'version'], check=True, capture_output=True)
    result = subprocess.check_output(['docker', 'info', '--format', '{{.OSType}}'], text=True)
    if result.strip() != 'linux':
        raise ValueError('Select Linux containers in Docker')
    if directory:
        path = Path(directory).resolve()
        ancestor = path
        while not ancestor.exists():
            ancestor = ancestor.parent
        if not ancestor.is_dir():
            raise ValueError('Configuration parent must be a directory')
        if validate_config and ((path / 'setup.json').exists() or (path / 'deployment.json').exists()):
            metadata, _ = read(path, require_credentials=False, draft=not (path / 'deployment.json').exists())
            if (path / 'deployment.json').exists() and compose.execute(path, 'ps', '-a', '-q', capture=True).stdout.strip():
                return
            check_ports(metadata)


def check_ports(metadata):
    ports = [metadata['dashboard_port']]
    if metadata['environment'] == 'dev':
        ports.append(metadata['vite_port'])
    if len(set(ports)) != len(ports):
        raise ValueError('Dashboard and Vite ports must differ')
    for port in ports:
        try:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', port))
        except OSError:
            raise ValueError(f'Local port {port} is unavailable; stop its owner or change the configured port') from None


def configure(directory, environment, project=None):
    directory = Path(directory).resolve()
    if directory.exists():
        with locked(directory):
            draft = not (directory / 'deployment.json').exists()
            metadata = read_metadata(directory, draft=draft)
            if metadata['environment'] != environment or (project and metadata['project'] != project):
                raise ValueError('Existing configuration belongs to another environment/project')
            path = directory / 'app.env'
            if not path.is_file():
                raise ValueError(f'{path}: existing app.env is missing; restore it before configure. Secrets will not be regenerated.')
            original = path.read_bytes()
            existing = env_template.parse(original.decode('utf-8-sig'), path)
            password = (directory / 'database-password').read_bytes().decode('utf-8').rstrip('\n')
            defaults = env_template.defaults(environment, password)
            missing = defaults.keys() - existing.keys()
            candidate = {**defaults, **existing}
            validate_values(directory, metadata, candidate, require_credentials=False, draft=draft)
            if missing:
                env_template.append_missing(path, original, '# Added by configure (existing values preserved)\n' + env_template.render(defaults, missing))
            return metadata
    return initialize(directory, environment, None, project, draft=True)


def build(directory, *, stage_directory=None):
    directory = Path(directory).resolve()
    with locked(directory):
        # Re-running installation must not rebuild a deployed release or rotate secrets.
        if (directory / 'deployment.json').exists():
            metadata, _ = read(directory)
            image_id(metadata['image'])
            return metadata
        metadata, _ = read(directory, draft=True)
        if metadata['environment'] == 'prod':
            if not stage_directory:
                raise ValueError('Production requires --stage-config; it never rebuilds Stage')
            stage, _ = read(stage_directory)
            if stage['environment'] != 'stage':
                raise ValueError('Promotion requires Stage configuration')
            image_id(stage['image'])
            reference = stage['image']
        else:
            tag = metadata['project'] + ':setup'
            subprocess.run(['docker', 'build', '-t', tag, '.'], cwd=compose.ROOT, check=True)
            reference = image_id(tag)
        metadata['image'] = reference
        write_json(directory / 'deployment.json', metadata)
        return metadata


def start(directory, *, stage_directory=None):
    metadata, _ = read(directory)
    # Bind-check only a first start; an existing project may already own its ports.
    existing = compose.execute(directory, 'ps', '-a', '-q', capture=True).stdout.strip()
    if not existing:
        check_ports(metadata)
    compose.up(directory, stage_directory)
    compose.execute(directory, 'up', '-d', '--no-deps', '--wait', '--wait-timeout', '120', *compose.APPLICATIONS)
    compose.execute(directory, 'run', '--rm', '--no-deps', '--entrypoint', 'python',
                    'dashboard', '-m', 'observability', 'snapshot')
