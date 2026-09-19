"""Local acceptance for isolated dev/stage/prod Compose projects.

Uses generated test credentials and a Bot fixture that loads real Cogs without
Discord login. Never uses existing application volumes or environment files.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from deploy import compose
from test_deployment import configure


def docker(*args, check=True):
    return subprocess.run(['docker', *args], check=check, capture_output=True, text=True, timeout=180)


def free_port():
    with socket.socket() as connection:
        connection.bind(('127.0.0.1', 0))
        return connection.getsockname()[1]


def container(directory, service):
    return compose.execute(directory, 'ps', '-a', '-q', service, capture=True).stdout.strip()


def sql(directory, statement):
    environment = json.loads((directory / 'deployment.json').read_text())['environment']
    return docker('exec', container(directory, 'postgres'), 'psql', '-U', 'postgres', '-d', 'tueka_' + environment,
                  '-v', 'ON_ERROR_STOP=1', '-Atc', statement).stdout.strip()


def ready(directory):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        bot = container(directory, 'bot')
        worker = container(directory, 'social-worker')
        dashboard = container(directory, 'dashboard')
        if bot and worker and dashboard:
            logs = docker('logs', bot, check=False)
            if 'Offline Bot extensions ready' in logs.stdout:
                probe = docker('exec', dashboard, 'python', '-c', "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8000/servers').status == 200", check=False)
                if probe.returncode == 0 and sql(directory, 'SELECT COUNT(*) FROM social_worker_state') != '0':
                    return
        time.sleep(1)
    raise RuntimeError('Compose services did not become ready')


def operational_snapshot(directory):
    code = "from runtime.environment import load_environment; load_environment(); import os,json; from observability.repository import snapshot; print(json.dumps(snapshot(os.environ['DATABASE_URL'])))"
    return json.loads(docker('exec', container(directory, 'dashboard'), 'python', '-c', code).stdout)


def monitoring_checks(directory):
    dashboard = container(directory, 'dashboard')
    def get(path):
        code = "import urllib.request,urllib.error;\ntry:\n r=urllib.request.urlopen('http://127.0.0.1:8000" + path + "',timeout=6); print(r.status)\nexcept urllib.error.HTTPError as e: print(e.code)"
        return int(docker('exec', dashboard, 'python', '-c', code).stdout.strip())
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if all(value['ready'] for value in operational_snapshot(directory)['services'].values()):
            break
        time.sleep(1)
    else:
        raise RuntimeError('Initial service readiness missing')
    for service in compose.APPLICATIONS:
        state = json.loads(docker('inspect', container(directory, service)).stdout)[0]
        assert state['HostConfig']['Memory'] == 768 * 1024 * 1024
        assert state['HostConfig']['NanoCpus'] == 1_000_000_000
        assert state['HostConfig']['PidsLimit'] == 128
        assert state['HostConfig']['LogConfig']['Config']['max-file'] == '3'
        assert state['Config']['Healthcheck']['Test']
    assert get('/internal/metrics') == 404
    assert get('/health/live?code=PRIVATE_QUERY') == 200
    sql(directory, "INSERT INTO social_events(provider,event_key,account_id,payload_json,received_at,status,available_at) VALUES('youtube','monitor_probe','offline','{\"value\":\"PRIVATE_PAYLOAD\"}',0,'failed',0)")
    assert 'dead_letter:social_events' in operational_snapshot(directory)['alerts']
    metrics = docker('exec', dashboard, 'python', '-c', "from runtime.environment import load_environment; load_environment(); import os,urllib.request; r=urllib.request.Request('http://127.0.0.1:8000/internal/metrics',headers={'Authorization':'Bearer '+os.environ['MONITORING_TOKEN']}); print(urllib.request.urlopen(r).read().decode())").stdout
    assert 'tueka_queue_failed{queue="social_events"} 1.0' in metrics
    assert 'PRIVATE_' not in metrics
    sql(directory, "DELETE FROM social_events WHERE event_key='monitor_probe'")
    compose.execute(directory, 'stop', 'social-worker')
    assert 'service_unavailable:social-worker' in operational_snapshot(directory)['alerts']
    compose.execute(directory, 'up', '-d', '--no-deps', 'social-worker')
    ready(directory)
    compose.execute(directory, 'stop', 'postgres')
    assert get('/health/live') == 200
    assert get('/health/ready') == 503
    compose.execute(directory, 'up', '-d', '--wait', 'postgres')
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if get('/health/ready') == 200 and all(value['ready'] for value in operational_snapshot(directory)['services'].values()):
            break
        time.sleep(2)
    else:
        raise RuntimeError('Services did not recover after database outage')
    logs = docker('logs', dashboard)
    assert 'PRIVATE_QUERY' not in logs.stdout + logs.stderr
    assert 'PRIVATE_PAYLOAD' not in logs.stdout + logs.stderr
    events = [json.loads(line) for line in logs.stdout.splitlines() if line.startswith('{')]
    assert any(event.get('event') == 'http_request' for event in events)
    print('monitoring: worker stop, failed delivery, database outage/recovery, safe logs and resource limits: OK', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--skip-dev', action='store_true')
    args = parser.parse_args()
    image = docker('image', 'inspect', '--format', '{{.Id}}', args.image).stdout.strip()
    unique = uuid.uuid4().hex[:12]
    original_command = compose.command
    directories = []
    overrides = {}
    (ROOT / '.venv-p0').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='p32-', dir=ROOT / '.venv-p0') as temporary:
        temporary = Path(temporary)
        bot_override = temporary / 'offline.json'
        bot_override.write_text(json.dumps({'services': {'bot': {
            'entrypoint': ['python', '-c', "exec(open('tests/fixtures/offline_bot.py').read())"],
            'command': [], 'restart': 'no'}}}), encoding='utf-8')

        def isolated_command(directory):
            base, env = original_command(directory)
            return [*base, '-f', str(bot_override), *overrides.get(str(directory), [])], env

        with patch('deploy.compose.command', side_effect=isolated_command):
            try:
                for environment in ('stage', 'prod', *(() if args.skip_dev else ('dev',))):
                    directory = temporary / environment
                    configure(directory, environment, image, f'tueka-{environment}-check-{unique}')
                    metadata = json.loads((directory / 'deployment.json').read_text())
                    metadata.update(dashboard_port=free_port(), vite_port=free_port())
                    (directory / 'deployment.json').write_text(json.dumps(metadata), encoding='utf-8')
                    directories.append(directory)
                stage, prod = directories[:2]
                for directory in directories:
                    rendered = json.loads(compose.execute(directory, 'config', '--format', 'json', capture=True).stdout)
                    environment = rendered['name'].split('-')[1]
                    assert not rendered['services']['postgres'].get('ports')
                    assert rendered['networks']['database']['internal']
                    for service in compose.APPLICATIONS:
                        app = rendered['services'][service]
                        assert app['read_only'] and app['user'] == '10001:10001'
                        assert app['depends_on']['migrate']['condition'] == 'service_completed_successfully'
                        assert not any('TOKEN' in key or 'DATABASE_URL' == key for key in app['environment'])
                        if environment != 'dev':
                            assert not any(v['type'] == 'bind' for v in app.get('volumes', []))
                    if environment == 'dev':
                        assert '--reload' in rendered['services']['dashboard']['command']
                        assert 'vite' in rendered['services']
                    else:
                        assert 'vite' not in rendered['services']
                compose.up(stage)
                ready(stage)
                monitoring_checks(stage)
                assert sql(stage, "SELECT rolsuper OR rolcreatedb OR rolcreaterole FROM pg_roles WHERE rolname='tueka_stage'") == 'f'
                compose.up(prod, stage)
                ready(prod)
                stage_volumes, prod_volumes, stage_networks, prod_networks = [], [], set(), set()
                for directory, volumes, networks in ((stage, stage_volumes, stage_networks), (prod, prod_volumes, prod_networks)):
                    for service in compose.APPLICATIONS:
                        state = json.loads(docker('inspect', container(directory, service)).stdout)[0]
                        assert state['Image'] == image
                        volumes.extend(m['Name'] for m in state['Mounts'] if m['Type'] == 'volume')
                        networks.update(state['NetworkSettings']['Networks'])
                    assert docker('exec', container(directory, 'dashboard'), 'python', '-c', "from pathlib import Path; assert not Path('/app/.env').exists()").returncode == 0
                assert not set(stage_volumes) & set(prod_volumes)
                assert not stage_networks & prod_networks
                sql(stage, 'SET ROLE tueka_stage; CREATE TABLE deployment_marker(value TEXT); INSERT INTO deployment_marker VALUES (\'preserved\')')
                docker('exec', container(stage, 'bot'), 'python', '-c', "from pathlib import Path; Path('/data/compose-proof').write_text('preserved')")
                docker('exec', container(stage, 'dashboard'), 'python', '-c', "from pathlib import Path; assert Path('/data/compose-proof').read_text() == 'preserved'")
                denied = docker('exec', container(stage, 'dashboard'), 'python', '-c', "from pathlib import Path; Path('/data/should-fail').write_text('x')", check=False)
                assert denied.returncode != 0
                docker('exec', container(prod, 'bot'), 'python', '-c', "from pathlib import Path; assert not Path('/data/compose-proof').exists()")
                compose.execute(stage, 'down')
                compose.up(stage)
                ready(stage)
                assert sql(stage, 'SELECT value FROM deployment_marker') == 'preserved'
                docker('exec', container(stage, 'bot'), 'python', '-c', "from pathlib import Path; assert Path('/data/compose-proof').read_text() == 'preserved'")
                print('stage/prod: same image ID, separate secrets/networks/volumes, persistent restart, readonly dashboard: OK', flush=True)

                migrations = temporary / 'migrations'
                shutil.copytree(ROOT / 'migrations/postgresql', migrations)
                next_version = len(list(migrations.glob('*.sql'))) + 1
                (migrations / f'{next_version:04d}_compose_probe.sql').write_text('ALTER TABLE deployment_marker ADD COLUMN revision BIGINT NOT NULL DEFAULT 1;\n', encoding='utf-8')
                migration_override = temporary / 'migration.json'
                migration_override.write_text(json.dumps({'services': {name: {'volumes': [{
                    'type': 'bind', 'source': str(migrations), 'target': '/app/migrations/postgresql', 'read_only': True
                }]} for name in (*compose.APPLICATIONS, 'migrate')}}), encoding='utf-8')
                overrides[str(stage)] = ['-f', str(migration_override)]
                compose.up(stage)
                ready(stage)
                assert sql(stage, 'SELECT value || revision FROM deployment_marker') == 'preserved1'
                bad = migrations / f'{next_version+1:04d}_failure.sql'
                bad.write_text('CREATE TABLE must_rollback(id BIGINT); INSERT INTO must_rollback VALUES (1/0);\n', encoding='utf-8')
                try:
                    compose.up(stage)
                except subprocess.CalledProcessError:
                    pass
                else:
                    raise AssertionError('Failed migration must block application startup')
                for service in compose.APPLICATIONS:
                    state = json.loads(docker('inspect', container(stage, service)).stdout)[0]['State']
                    assert not state['Running']
                assert sql(stage, "SELECT COUNT(*) FROM pg_tables WHERE tablename='must_rollback'") == '0'
                bad.unlink()
                compose.up(stage)
                ready(stage)
                assert sql(stage, 'SELECT value || revision FROM deployment_marker') == 'preserved1'
                print('schema upgrade preserves data; migration failure stops writers, rolls back, and recovers: OK', flush=True)

                if not args.skip_dev:
                    dev = directories[2]
                    compose.up(dev)
                    ready(dev)
                    vite = container(dev, 'vite')
                    deadline = time.monotonic() + 120
                    while time.monotonic() < deadline:
                        result = docker('exec', vite, 'node', '-e', "Promise.all([['/servers',200],['/api/v1/session',401],['/api/openapi.json',404]].map(([p,s])=>fetch('http://127.0.0.1:5173'+p).then(r=>{if(r.status!==s)throw Error(r.status)}))).catch(()=>process.exit(1))", check=False)
                        if result.returncode == 0:
                            break
                        time.sleep(2)
                    else:
                        raise RuntimeError('Vite SPA or backend proxy failed')
                    pid_probe = "import json; print(json.load(open('/tmp/tueka-health-dashboard.json'))['pid'])"
                    previous_pid = docker('exec', container(dev, 'dashboard'), 'python', '-c', pid_probe).stdout.strip()
                    probe = ROOT / 'runtime' / ('_compose_reload_' + unique + '.py')
                    try:
                        probe.write_text('# Temporary Compose reload acceptance probe\n', encoding='utf-8')
                        deadline = time.monotonic() + 30
                        while time.monotonic() < deadline:
                            current_pid = docker('exec', container(dev, 'dashboard'), 'python', '-c', pid_probe).stdout.strip()
                            if current_pid != previous_pid:
                                break
                            time.sleep(1)
                        else:
                            raise RuntimeError('Source change did not trigger Uvicorn reload')
                    finally:
                        probe.unlink(missing_ok=True)
                    ready(dev)
                    print('dev: source mounts, Uvicorn reload, Vite SPA and same-origin API proxy: OK', flush=True)
            except Exception:
                for directory in directories:
                    for service in ('postgres', 'migrate', *compose.APPLICATIONS, 'vite'):
                        try:
                            identifier = container(directory, service)
                            if identifier:
                                result = docker('logs', '--tail', '30', identifier, check=False)
                                print(service + ': ' + result.stdout + result.stderr, flush=True)
                        except subprocess.CalledProcessError:
                            pass
                raise
            finally:
                for directory in reversed(directories):
                    # Only UUID-owned acceptance projects may lose their temporary volumes.
                    metadata = json.loads((directory / 'deployment.json').read_text())
                    assert metadata['project'].endswith('-check-' + unique)
                    compose.execute(directory, 'down', '-v', '--remove-orphans')


if __name__ == '__main__':
    main()
