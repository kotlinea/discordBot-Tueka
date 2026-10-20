"""Resumable first installation; delegates all database operations to Compose."""
import json
import os
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
        if os.environ.get('TUEKA_DOCKER_MANAGER') == '1':
            from .docker_bridge import port_probe
            try:
                port_probe(port)
            except subprocess.CalledProcessError:
                raise ValueError(f'Host port {port} is unavailable; stop its owner or change dashboard_port/vite_port in the selected deployment.json or setup.json') from None
            continue
        try:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', port))
        except OSError:
            raise ValueError(f'Local port {port} is unavailable; stop its owner or change the configured port') from None


def _require_configuration_files(directory):
    missing_files = [str(directory / name) for name in ('app.env', 'database-password', 'postgres-admin-password')
                     if not (directory / name).is_file()]
    if missing_files:
        raise ValueError(
            f'Incomplete configuration; missing required files: {", ".join(missing_files)}. '
            'app.env and metadata alone are not a complete configuration. '
            'For a new environment, select an empty --config-dir and let configure generate all files before editing app.env. '
            'For an existing environment, restore its matching files. No secrets were regenerated.'
        )


def configure(directory, environment, project=None):
    directory = Path(directory).resolve()
    try:
        # Some Host bind mounts return EEXIST, not ENOENT, for missing parents.
        # Create from the first missing parent rather than relying on errno recursion.
        for parent in (*reversed(directory.parents), directory):
            if not parent.is_dir():
                parent.mkdir(exist_ok=True)
    except FileExistsError as error:
        conflict = Path(error.filename) if error.filename else directory
        if conflict.is_file():
            detail = 'The path is a file; select a directory with --config-dir.'
        else:
            detail = ('The OS reports that this path exists, but it is not accessible as a directory. '
                      'Compare this path on the Host and in the Docker bind mount, including parent paths. '
                      'Check filesystem access and Docker file sharing before retrying.')
        raise ValueError(f'Cannot create configuration directory (EEXIST): {conflict}. {detail}') from None
    with locked(directory):
        if not any(path.name != '.recovery.lock' for path in directory.iterdir()):
            return initialize(directory, environment, None, project, draft=True, existing_empty=True)
        if not any((directory / name).is_file() for name in ('setup.json', 'deployment.json')):
            raise ValueError(f'Incomplete configuration: {directory}. setup.json or deployment.json is missing. Restore the matching configuration, or select an empty directory with --config-dir. Existing secrets were preserved.')
        _require_configuration_files(directory)
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


def build(directory, *, stage_directory=None):
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ValueError(
            f'Configuration directory is missing or is not a directory: {directory}. '
            'Build requires the same --config-dir used by setup configure. '
            'If configure has not succeeded for this environment, run setup configure with '
            '--environment dev, stage or prod and this --config-dir, then fill in app.env before build. '
            'No application image build was started.'
        )
    with locked(directory):
        if not any((directory / name).is_file() for name in ('setup.json', 'deployment.json')):
            raise ValueError(
                f'Configuration metadata is missing: {directory / "setup.json"} '
                f'or {directory / "deployment.json"}. '
                'Use the --config-dir where setup configure succeeded. '
                'For an empty directory run setup configure first; for a partial configuration restore its matching files. '
                'No application image build was started.'
            )
        # Re-running installation must not rebuild a deployed release or rotate secrets.
        _require_configuration_files(directory)
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
    with locked(directory):
        metadata, _ = read(directory)
        # Bind-check only a first start; an existing project may already own its ports.
        existing = compose.execute(directory, 'ps', '-a', '-q', capture=True).stdout.strip()
        if not existing:
            check_ports(metadata)
        # Keep the writer-starting readiness call inside the same recovery lock.
        compose._up(directory, stage_directory)
        compose.execute(directory, 'up', '-d', '--no-deps', '--wait', '--wait-timeout', '120', *compose.APPLICATIONS)
        compose.execute(directory, 'run', '--rm', '--no-deps', '--entrypoint', 'python',
                        'dashboard', '-m', 'observability', 'snapshot')
