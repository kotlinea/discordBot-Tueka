"""Exercise backup, encrypted recovery and older-image rollback in UUID projects."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'scripts')]
from cryptography.fernet import Fernet
from deploy import compose
from deploy.recovery import restore, release, abort, digest, load_bundle
from deploy.backup_job import run as scheduled_backup
from test_deployment import configure
from verify_compose import docker, container, free_port, ready, sql


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    args = parser.parse_args()
    image = docker('image', 'inspect', '--format', '{{.Id}}', args.image).stdout.strip()
    unique = uuid.uuid4().hex[:12]
    directories = []
    upgraded_tag = 'tueka-recovery-upgrade:' + unique
    base_tag = 'tueka-recovery-base:' + unique
    original = compose.command
    (ROOT / '.tools-runs').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='p34-', dir=ROOT / '.tools-runs') as temporary:
        root = Path(temporary)
        offline = root / 'offline.json'
        offline.write_text(json.dumps({'services': {'bot': {'entrypoint': ['python', '-c', "exec(open('tests/fixtures/offline_bot.py').read())"], 'command': [], 'restart': 'no'}}}))
        def command(directory):
            base, env = original(directory)
            return [*base, '-f', str(offline)], env
        keys = {name: Fernet.generate_key().decode() for name in ('TICKET_ENCRYPTION_KEY', 'SOCIAL_TOKEN_ENCRYPTION_KEY')}
        with patch('deploy.compose.command', side_effect=command):
            try:
                for suffix in ('source', 'restored', 'failed'):
                    directory = root / suffix
                    configure(directory, 'stage', image, f'tueka-stage-recovery-{suffix}-{unique}')
                    metadata = json.loads((directory / 'deployment.json').read_text())
                    metadata['dashboard_port'] = free_port()
                    (directory / 'deployment.json').write_text(json.dumps(metadata))
                    with (directory / 'app.env').open('a') as env:
                        env.write(''.join(name + '=' + value + '\n' for name, value in keys.items()))
                    directories.append(directory)
                source, target, failed = directories
                compose.up(source)
                ready(source)
                fixture = (ROOT / 'tests/fixtures/recovery_state.py').read_text()
                docker('exec', container(source, 'bot'), 'python', '-c', fixture + '\nasyncio.run(seed())')
                job_config = root / 'backup.json'
                job_options = {'version': 1, 'enabled': False, 'minimum_free_gib': 1,
                    'environments': [{'config_dir': str(source), 'backup_root': str(root / 'snapshots')}],
                    'smtp': {'enabled': False}}
                job_config.write_text(json.dumps(job_options))
                assert scheduled_backup(job_config) == {'status': 'disabled'}
                assert not (root / 'snapshots').exists()
                job_options['enabled'] = True
                job_config.write_text(json.dumps(job_options))
                job_result = scheduled_backup(job_config)
                assert job_result['status'] == 'backed-up' and len(job_result['bundles']) == 1
                bundle = Path(job_result['bundles'][0])
                manifest = load_bundle(bundle)
                assert manifest['observations']['verified_blobs'] == 2
                assert manifest['observations']['verified_encrypted_values'] == 3
                ready(source)
                assert (bundle / 'database.dump').read_bytes()[:5] == b'PGDMP'
                assert all(value not in (bundle / 'manifest.json').read_text() for value in keys.values())
                corrupt = root / 'corrupt'
                shutil.copytree(bundle, corrupt)
                (corrupt / 'database.dump').write_bytes(b'broken')
                try:
                    restore(target, corrupt, source_directory=source)
                except ValueError:
                    pass
                else:
                    raise AssertionError('Corrupt bundle accepted')
                assert not (target / 'recovery-pending.json').exists()

                # A checksum-valid but invalid dump must roll back and keep writers held.
                corrupt_manifest = json.loads((corrupt / 'manifest.json').read_text())
                corrupt_manifest['artifacts']['database.dump'] = digest(corrupt / 'database.dump')
                (corrupt / 'manifest.json').write_text(json.dumps(corrupt_manifest))
                try:
                    restore(failed, corrupt, source_directory=source)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError('Invalid native dump accepted')
                assert sql(failed, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'") == '0'
                assert (failed / 'recovery-pending.json').exists()
                abort(failed, source)
                try:
                    compose.up(failed)
                except ValueError:
                    pass
                else:
                    raise AssertionError('Aborted recovery target was started')
                compose.up(source)
                ready(source)

                # Exercise a genuine newer image and schema, then return to the snapshot image/schema.
                upgrade = root / 'upgrade'
                upgrade.mkdir()
                (upgrade / '0003_recovery_probe.sql').write_text('CREATE TABLE recovery_upgrade_probe(id BIGINT);\n')
                docker('tag', image, base_tag)
                (upgrade / 'Dockerfile').write_text(f'FROM {base_tag}\nCOPY 0003_recovery_probe.sql /app/migrations/postgresql/0003_recovery_probe.sql\n')
                result = docker('build', '-t', upgraded_tag, str(upgrade), check=False)
                if result.returncode:
                    raise RuntimeError('Isolated upgrade image build failed: ' + result.stderr)
                newer = docker('image', 'inspect', '--format', '{{.Id}}', upgraded_tag).stdout.strip()
                assert newer != image
                metadata = json.loads((source / 'deployment.json').read_text())
                metadata['image'] = newer
                (source / 'deployment.json').write_text(json.dumps(metadata))
                compose.up(source)
                ready(source)
                sql(source, "UPDATE app_metadata SET value='new' WHERE key='recovery_version'")
                restored = restore(target, bundle, source_directory=source)
                assert restored['verified_blobs'] == 2 and restored['verified_encrypted_values'] == 3
                for directory in (source, target):
                    try:
                        compose.up(directory)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError('Recovery fence/hold did not block startup')
                try:
                    release(target)
                except ValueError:
                    pass
                else:
                    raise AssertionError('Unreconciled release accepted')
                release(target, reconciled=True)
                # Real domain Service/Runner with an offline external receipt Port.
                base, env = compose.command(target)
                subprocess.run([*base, 'run', '--rm', '--no-deps', '-T', '--entrypoint', 'python', 'recovery-data', '-c', fixture + '\nasyncio.run(resume())'], env=env, check=True)
                compose.up(target)
                ready(target)
                assert docker('inspect', '--format', '{{.Image}}', container(target, 'dashboard')).stdout.strip() == image
                assert sql(target, 'SELECT MAX(version) FROM schema_migrations') == '2'
                assert sql(source, 'SELECT MAX(version) FROM schema_migrations') == '3'
                assert sql(source, "SELECT value FROM app_metadata WHERE key='recovery_version'") == 'new'
                def volume(directory, service, destination):
                    return next(m['Name'] for m in json.loads(docker('inspect', container(directory, service)).stdout)[0]['Mounts'] if m['Destination'] == destination)
                source_volume = volume(source, 'postgres', '/var/lib/postgresql')
                target_volume = volume(target, 'postgres', '/var/lib/postgresql')
                assert source_volume != target_volume
                assert volume(source, 'bot', '/data') != volume(target, 'bot', '/data')
                print('config opt-in backup job/resume, separate-volume DB+encrypted blobs/keys, failed restore/abort, held writers, receipt recovery, older image/schema rollback: OK', flush=True)
            finally:
                for directory in reversed(directories):
                    try:
                        compose.execute(directory, 'down', '-v', '--remove-orphans')
                    except Exception:
                        pass
                docker('image', 'rm', upgraded_tag, check=False)
                docker('image', 'rm', base_tag, check=False)


if __name__ == '__main__':
    main()
