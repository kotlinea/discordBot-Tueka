"""Quiesce a Compose environment and restore a matched snapshot into a new project."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from . import compose
from .configuration import read
from .locking import locked
from recovery.storage import key_generations

ARTIFACTS = ('database.dump', 'transcripts.tar')
PENDING = 'recovery-pending.json'
FENCE = 'recovery-fence.json'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def operation(directory, service, action, *, source=None, output=None):
    base, env = compose.command(directory)
    result = subprocess.run([*base, 'run', '--rm', '--no-deps', '-T', service, action],
        env=env, stdin=source, stdout=output if output is not None else subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=1800)
    if result.returncode:
        raise RuntimeError(f'Recovery {service}/{action} failed; services remain stopped')
    return result.stdout


def running(directory):
    # Compose's service listing is not proof of container liveness, especially
    # after recreation. Inspect all instances, including stopped/restarting ones.
    active = set()
    for service in compose.APPLICATIONS:
        identifiers = compose.execute(directory, 'ps', '-a', '-q', service, capture=True).stdout.split()
        if not identifiers:
            continue
        output = subprocess.check_output(
            ['docker', 'inspect', '--format', '{{json .State}}', *identifiers], text=True)
        container_states = [json.loads(line) for line in output.splitlines()]
        if len(container_states) != len(identifiers):
            raise RuntimeError('Could not verify every application container state')
        if any(state['Running'] or state['Restarting'] for state in container_states):
            active.add(service)
    return active


def image_id(reference):
    return subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', reference], text=True).strip()


def load_bundle(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format') != 1 or set(manifest.get('artifacts', {})) != set(ARTIFACTS):
        raise ValueError('Unsupported or incomplete recovery bundle')
    for name in ARTIFACTS:
        path = directory / name
        if path.is_symlink() or digest(path) != manifest['artifacts'][name]:
            raise ValueError('Recovery artifact checksum mismatch')
    return manifest


def backup(directory, destination, *, resume_source=False):
    directory, destination = Path(directory).resolve(), Path(destination).resolve()
    config, secrets = read(directory)
    if config['environment'] == 'dev':
        raise ValueError('Image-matched recovery bundles require Stage or production; Dev uses mutable source mounts')
    if any((directory / name).exists() for name in (PENDING, FENCE)):
        raise ValueError('Cannot back up an unreleased recovery environment')
    resolved = image_id(config['image'])
    if not compose.execute(directory, 'ps', '-a', '-q', 'postgres', capture=True).stdout.strip():
        raise ValueError('Backup requires an existing PostgreSQL service')
    # Check stopped containers too: configuration alone does not prove the running version.
    for service in compose.APPLICATIONS:
        identifier = compose.execute(directory, 'ps', '-a', '-q', service, capture=True).stdout.strip()
        if identifier and subprocess.check_output(['docker', 'inspect', '--format', '{{.Image}}', identifier], text=True).strip() != resolved:
            raise ValueError('Application containers differ from the snapshot image')
    destination.mkdir(parents=True, exist_ok=False)
    destination.chmod(0o700)
    with locked(directory):
        if any((directory / name).exists() for name in (PENDING, FENCE)):
            raise ValueError('Cannot back up an unreleased recovery environment')
        was_running = running(directory)
        compose.execute(directory, 'stop', *compose.APPLICATIONS)
        compose.execute(directory, 'up', '-d', '--wait', 'postgres')
        operation(directory, 'recovery-db', 'idle')
        observations = json.loads(operation(directory, 'recovery-data', 'verify'))
        for name, service in zip(ARTIFACTS, ('recovery-db', 'recovery-data')):
            path = destination / name
            with path.open('xb') as output:
                path.chmod(0o600)
                operation(directory, service, 'backup' if name == 'database.dump' else 'export', output=output)
        operation(directory, 'recovery-db', 'idle')
        manifest = {'format': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
            'environment': config['environment'], 'source_project': config['project'],
            'image_id': resolved, 'image_reference': config['image'],
            'discord_client_id': secrets['DISCORD_CLIENT_ID'], 'key_generations': key_generations(secrets),
            'observations': observations, 'artifacts': {name: digest(destination / name) for name in ARTIFACTS}}
        write_json(destination / 'manifest.json', manifest)
        if resume_source and was_running:
            compose.execute(directory, 'up', '-d', '--no-deps', '--wait', '--wait-timeout', '120', *sorted(was_running))
    return manifest


def validate_target(config, secrets, manifest):
    if secrets.get('TICKET_S3_BUCKET'):
        raise ValueError('Restore materializes local blobs; disable target S3 until recovery is released')
    if config['project'] == manifest['source_project'] or config['environment'] != manifest['environment']:
        raise ValueError('Restore requires a separate project in the same environment')
    if secrets['DISCORD_CLIENT_ID'] != manifest['discord_client_id']:
        raise ValueError('Restore must retain the original Discord application identity')
    if key_generations(secrets) != manifest['key_generations']:
        raise ValueError('Recovery encryption key generation mismatch')
    if image_id(config['image']) != manifest['image_id']:
        raise ValueError('Restore requires the snapshot application image')


def restore(directory, bundle, *, source_directory=None, source_fenced=False):
    directory, bundle = Path(directory).resolve(), Path(bundle).resolve()
    manifest = load_bundle(bundle)
    config, secrets = read(directory)
    validate_target(config, secrets, manifest)
    if not source_directory and not source_fenced:
        raise ValueError('Specify the source configuration or attest that its writers are fenced')
    if any((directory / name).exists() for name in (PENDING, FENCE)) or running(directory):
        raise ValueError('Target is running or already has a recovery hold')
    with locked(directory):
        if any((directory / name).exists() for name in (PENDING, FENCE)) or running(directory):
            raise ValueError('Target is running or already has a recovery hold')
        pending = {'bundle': str(bundle), 'source_config': str(Path(source_directory).resolve()) if source_directory else None,
                   'source_fenced': bool(source_fenced), 'status': 'restoring'}
        write_json(directory / PENDING, pending)
        if source_directory:
            source_directory = Path(source_directory).resolve()
            source, _ = read(source_directory)
            if source['project'] != manifest['source_project']:
                raise ValueError('Source project does not match the snapshot')
            with locked(source_directory):
                if (source_directory / FENCE).exists() or (source_directory / PENDING).exists():
                    raise ValueError('Source already belongs to another recovery operation')
                compose.execute(source_directory, 'stop', *compose.APPLICATIONS)
                if running(source_directory):
                    raise ValueError('Source writers are still running')
                write_json(source_directory / FENCE, {'target_project': config['project'], 'target_config': str(directory)})
        compose.execute(directory, 'up', '-d', '--wait', 'postgres')
        operation(directory, 'recovery-db', 'empty')
        operation(directory, 'recovery-db', 'idle')
        operation(directory, 'recovery-data', 'empty')
        with (bundle / 'transcripts.tar').open('rb') as stream:
            operation(directory, 'recovery-data', 'import', source=stream)
        with (bundle / 'database.dump').open('rb') as stream:
            operation(directory, 'recovery-db', 'restore', source=stream)
        verification = json.loads(operation(directory, 'recovery-data', 'localize'))
        if verification['migrations'] != manifest['observations']['migrations'] or verification['queues'] != manifest['observations']['queues']:
            raise ValueError('Restored migration/queue state differs from the snapshot')
        pending.update(status='verified-awaiting-reconciliation', verification=verification)
        write_json(directory / PENDING, pending)
    return verification


def abort(directory, source_directory):
    """Keep the incomplete target blocked; allow the preserved source to restart."""
    directory, source_directory = Path(directory).resolve(), Path(source_directory).resolve()
    with locked(directory), locked(source_directory):
        pending = json.loads((directory / PENDING).read_text(encoding='utf-8'))
        fence = json.loads((source_directory / FENCE).read_text(encoding='utf-8'))
        if pending['source_config'] != str(source_directory) or fence['target_config'] != str(directory) or running(directory):
            raise ValueError('Cannot abort a running target or a different recovery')
        pending['status'] = 'aborted-do-not-start'
        write_json(directory / PENDING, pending)
        (source_directory / FENCE).unlink()


def release(directory, *, reconciled=False):
    directory = Path(directory).resolve()
    if not reconciled:
        raise ValueError('External Discord receipts and post-snapshot actions must be reconciled before release')
    with locked(directory):
        pending = json.loads((directory / PENDING).read_text(encoding='utf-8'))
        if pending['status'] != 'verified-awaiting-reconciliation' or running(directory):
            raise ValueError('Recovery must be verified and target writers stopped')
        if pending['source_config']:
            source = Path(pending['source_config'])
            fence = json.loads((source / FENCE).read_text(encoding='utf-8'))
            if fence['target_config'] != str(directory) or running(source):
                raise ValueError('Source is not fenced for this recovery')
        elif not pending['source_fenced']:
            raise ValueError('Source fencing is required')
        config, secrets = read(directory)
        validate_target(config, secrets, load_bundle(pending['bundle']))
        verification = json.loads(operation(directory, 'recovery-data', 'verify'))
        write_json(directory / 'recovery-release.json', {'released_at': datetime.now(timezone.utc).isoformat(),
            'bundle': pending['bundle'], 'external_state_reconciled': True, 'verification': verification})
        (directory / PENDING).unlink()
    return verification
