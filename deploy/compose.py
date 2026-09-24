"""Stop old writers, rerun migration, then start the environment's services."""
import json
import os
from pathlib import Path
import subprocess

from .configuration import read, read_metadata, validate_promotion
from .locking import locked

ROOT = Path(__file__).resolve().parents[1]
APPLICATIONS = ('bot', 'dashboard', 'social-worker')


def command(directory):
    directory = Path(directory).resolve()
    config = read_metadata(directory)
    env = {key: value for key, value in os.environ.items() if not key.startswith('COMPOSE_')}
    env.update(TUEKA_ENV=config['environment'], APP_IMAGE=config['image'], TUEKA_CONFIG_DIR=str(directory),
               DEV_IMAGE=config['project'] + '-development:local',
               DASHBOARD_PORT=str(config['dashboard_port']), VITE_PORT=str(config['vite_port']))
    args = ['docker', 'compose', '--env-file', str(ROOT / 'deploy/compose.env'), '--project-directory', str(ROOT),
            '-p', config['project'], '-f', str(ROOT / 'deploy/compose.yaml'),
            '-f', str(ROOT / f'deploy/compose.{config["environment"]}.yaml')]
    return args, env


def execute(directory, *args, capture=False):
    base, env = command(directory)
    return subprocess.run([*base, *args], env=env, cwd=ROOT, check=True, text=True,
                          capture_output=capture)


def up(directory, stage_directory=None):
    if any((Path(directory) / name).exists() for name in ('.recovery.lock', 'recovery-pending.json', 'recovery-fence.json')):
        raise ValueError('Recovery is active or awaiting reconciliation; use the recovery release command')
    with locked(directory):
        return _up(directory, stage_directory)


def _up(directory, stage_directory=None):
    if any((Path(directory) / name).exists() for name in ('recovery-pending.json', 'recovery-fence.json')):
        raise ValueError('Recovery is awaiting reconciliation')
    config, _ = read(directory)
    if config['environment'] == 'prod':
        if not stage_directory:
            raise ValueError('Production requires --stage-config to verify image promotion')
        validate_promotion(stage_directory, directory)
        output = execute(stage_directory, 'ps', '--format', 'json', *APPLICATIONS, capture=True).stdout.strip()
        stage_state = json.loads(output) if output.startswith('[') else [json.loads(line) for line in output.splitlines()]
        if isinstance(stage_state, dict):
            stage_state = [stage_state]
        if {item['Service'] for item in stage_state} != set(APPLICATIONS) or any(item['State'] != 'running' for item in stage_state):
            raise ValueError('All Stage application services must be running before promotion')
        # Resolve immutable IDs; a running older image is not accepted as this release.
        expected = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', config['image']], text=True).strip()
        for item in stage_state:
            actual = subprocess.check_output(['docker', 'inspect', '--format', '{{.Image}}', item['ID']], text=True).strip()
            if actual != expected:
                raise ValueError('Running Stage image differs from the requested release')
    execute(directory, 'config', '--quiet')
    if config['environment'] == 'dev':
        # The read-only frontend bind hides the image's node_modules directory.
        # Docker needs a host mountpoint before mounting the nested named volume.
        (ROOT / 'dashboard/frontend/node_modules').mkdir(exist_ok=True)
        execute(directory, 'build', 'vite')
    else:
        # Resolve/download before stopping existing writers.
        if '@sha256:' in config['image']:
            subprocess.run(['docker', 'pull', config['image']], check=True)
    subprocess.run(['docker', 'image', 'inspect', config['image']], stdout=subprocess.DEVNULL, check=True)
    execute(directory, 'stop', *APPLICATIONS)
    execute(directory, 'up', '-d', '--wait', 'postgres')
    execute(directory, 'rm', '-f', 'migrate')
    execute(directory, 'up', '-d', 'migrate')
    try:
        execute(directory, 'wait', 'migrate')
    except subprocess.CalledProcessError:
        raise ValueError(
            f'Migration failed; application services remain stopped. '
            f'Inspect: docker logs --tail 100 {config["project"]}-migrate-1. '
            f'Configuration: {Path(directory).resolve() / "app.env"} (DATABASE_URL), '
            f'{Path(directory).resolve() / "database-password"}. '
            'PostgreSQL healthy only confirms readiness, not application authentication. '
            'For an existing volume, restore its matching credentials; do not regenerate secrets or delete the volume. '
            'Correct the reported cause, then retry the same start/up command.'
        ) from None
    execute(directory, 'up', '-d', '--no-deps', *APPLICATIONS, *(['vite'] if config['environment'] == 'dev' else []))
