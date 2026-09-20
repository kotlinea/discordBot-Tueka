"""Compose task entrypoint. Host dependencies are Git and Linux Docker only."""
import argparse
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid

SOURCE = Path('/workspace')
GROUPS = {
    'python': ['test-python', 'api-check', 'commands-check', 'check-docs', 'verify-restore', 'verify-tools'],
    'web': ['typecheck', 'test-web', 'build-web', 'build-docs', 'test-a11y', 'test-docs-a11y'],
    'runtime': ['build-image', 'verify-runtime', 'verify-compose', 'verify-setup', 'verify-recovery', 'verify-caddy'],
    'secrets': ['secrets'],
}
IGNORED = {'.git', '.idea', '.codex', '.agents', '.hallmark', 'node_modules', '__pycache__',
           'data', 'artifacts', '.tools-runs', 'dist', 'test-results', 'playwright-report',
           'app.env', 'setup.json', 'deployment.json', 'database-password', 'postgres-admin-password',
           'backups', 'ticket-transcripts', 'cache', 'vite.config.js', 'vite.config.d.ts'}


def ignored(directory, names):
    return [name for name in names if name in IGNORED or name.startswith(('.env', '.venv'))
            or name.endswith(('.pyc', '.tsbuildinfo', '.log', '.dump', '.db', '.sqlite3'))]


def copy_source(target):
    shutil.copytree(SOURCE, target, ignore=ignored, dirs_exist_ok=True)


def ownership(path, reference=SOURCE):
    if os.name != 'posix':
        return
    info = reference.stat()
    os.chown(path, info.st_uid, info.st_gid)


def writeback(source, relative):
    target = SOURCE / relative
    if target.is_symlink() or not target.resolve().is_relative_to(SOURCE.resolve()):
        raise ValueError(f'{relative}: generated output must be a regular file inside the checkout')
    missing, parent = [], target.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    target.parent.mkdir(parents=True, exist_ok=True)
    for directory in missing:
        ownership(directory, parent)
    reference = target if target.exists() else SOURCE
    info = reference.stat()
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(source.read_bytes())
    try:
        temporary.chmod(info.st_mode & 0o777 if target.exists() else 0o644)
        ownership(temporary, reference)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def command(args, *, cwd, log, env=None):
    process = subprocess.Popen(args, cwd=cwd, env=env, start_new_session=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, errors='replace')
    try:
        for line in process.stdout:
            print(line, end='', flush=True)
            log.write(line)
            log.flush()
        code = process.wait()
    except BaseException:
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=45)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        raise
    if code:
        raise subprocess.CalledProcessError(code, args)


def manager_state():
    sys.path.insert(0, '/opt/tool-code')
    from deploy.docker_bridge import inspect_self
    return inspect_self()


def check_dependencies(task, installed=Path('/opt')):
    if task in ('lock-python', 'lock-web'):
        return  # Lock repair cannot depend on an already matching lock.
    pairs = [(installed / 'requirements.lock', SOURCE / 'requirements.lock')]
    for directory in ('dashboard/frontend', 'docs'):
        pairs.extend((installed / 'deps' / directory / name, SOURCE / directory / name)
                     for name in ('package.json', 'package-lock.json'))
    for image_file, source_file in pairs:
        if image_file.exists() and image_file.read_bytes() != source_file.read_bytes():
            raise ValueError(f'{source_file}: tool image dependencies are stale. Rerun docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build {task} with the same arguments.')


def run(task, args, root, log):
    check_dependencies(task)
    def call(*items, cwd=root, env=None):
        command(list(items), cwd=cwd, log=log, env=env)
    python = sys.executable
    if task == 'check':
        call('docker', 'info', '--format', '{{.OSType}}')
        if subprocess.check_output(['docker', 'info', '--format', '{{.OSType}}'], text=True).strip() != 'linux':
            raise ValueError('Docker must use Linux containers')
        call('docker', 'compose', 'version')
        manager_state()
        probe = SOURCE / '.tools-runs' / ('check-' + uuid.uuid4().hex)
        probe.parent.mkdir(exist_ok=True)
        probe.write_text('writable')
        probe.unlink()
        print('Linux Docker, Compose, source mount and artifact writes: OK')
    elif task in ('setup', 'deploy', 'recovery'):
        call(python, f'scripts/{task}.py', *args)
    elif task == 'test-python':
        call(python, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py', *args)
    elif task in ('api-check', 'api-generate', 'commands-check', 'commands-generate'):
        name = 'api' if task.startswith('api') else 'commands'
        extra = ['--check'] if task.endswith('check') else (['--write'] if name == 'commands' else [])
        call(python, f'scripts/generate_{name}.py', *extra, *args)
        if task.endswith('generate'):
            paths = ['dashboard/api/openapi.json', 'dashboard/frontend/src/generated/api.ts'] if name == 'api' else [
                'docs/reference/commands.json', 'docs/reference/commands.md', 'docs/en/reference/commands.md']
            for relative in paths:
                writeback(root / relative, relative)
    elif task == 'check-docs':
        call(python, 'scripts/check_documentation.py', *args)
    elif task == 'lock-python':
        call('uv', 'pip', 'compile', 'requirements.txt', '--python-version', '3.13', '--universal',
             '--generate-hashes', '--output-file', 'requirements.lock', *args)
        writeback(root / 'requirements.lock', 'requirements.lock')
    elif task == 'lock-web':
        for directory in ('dashboard/frontend', 'docs'):
            call('npm', '--prefix', directory, 'install', '--package-lock-only', '--ignore-scripts', '--no-audit', '--no-fund', *args)
            writeback(root / directory / 'package-lock.json', directory + '/package-lock.json')
    elif task in ('typecheck', 'test-web', 'build-web', 'build-docs', 'test-a11y', 'test-docs-a11y', 'dev-web', 'dev-docs'):
        for directory in ('dashboard/frontend', 'docs'):
            (root / directory / 'node_modules').symlink_to(Path('/opt/deps') / directory / 'node_modules')
        if task == 'test-docs-a11y':
            call('npm', '--prefix', 'docs', 'run', 'build')
        directory, script = {
            'typecheck': ('dashboard/frontend', 'typecheck'), 'test-web': ('dashboard/frontend', 'test'),
            'build-web': ('dashboard/frontend', 'build'), 'build-docs': ('docs', 'build'),
            'test-a11y': ('dashboard/frontend', 'test:a11y'), 'test-docs-a11y': ('dashboard/frontend', 'test:docs-a11y'),
            'dev-web': ('dashboard/frontend', 'dev'), 'dev-docs': ('docs', 'dev'),
        }[task]
        watcher = None
        if task.startswith('dev-'):
            # Mirror source changes without exposing container dependencies on Host.
            import threading
            stop = threading.Event()
            def sync():
                previous = {p.relative_to(root) for p in (root / directory).rglob('*')
                            if p.is_file() and not any(part in IGNORED for part in p.relative_to(root).parts)}
                while not stop.wait(1):
                    current = set()
                    for base, dirs, files in os.walk(SOURCE / directory):
                        dirs[:] = [d for d in dirs if d not in ignored(base, dirs)]
                        for name in files:
                            if name in ignored(base, [name]):
                                continue
                            source = Path(base) / name
                            try:
                                content = source.read_bytes()
                            except FileNotFoundError:
                                continue
                            current.add(source.relative_to(SOURCE))
                            target = root / source.relative_to(SOURCE)
                            if not target.exists() or content != target.read_bytes():
                                target.parent.mkdir(parents=True, exist_ok=True)
                                target.write_bytes(content)
                    for relative in previous - current:
                        (root / relative).unlink(missing_ok=True)
                    previous = current
                    tokens = SOURCE / 'tokens.css'
                    if tokens.read_bytes() != (root / 'tokens.css').read_bytes():
                        shutil.copyfile(tokens, root / 'tokens.css')
            watcher = threading.Thread(target=sync, daemon=True)
            watcher.start()
            args = ['--host', '0.0.0.0', '--port', '5173' if task == 'dev-web' else '5174', *args]
        try:
            call('npm', '--prefix', directory, 'run', script, *(['--', *args] if args else []))
        finally:
            if watcher:
                stop.set()
                watcher.join(timeout=10)
        if task in ('build-docs', 'test-docs-a11y'):
            call(python, 'scripts/check_documentation.py', '--built')
    elif task == 'build-image':
        call('docker', 'build', '-t', os.environ.get('TUEKA_TOOLS_IMAGE', 'tueka:tools'), *args, '.')
    elif task.startswith('verify-'):
        image = os.environ.get('TUEKA_TOOLS_IMAGE', 'tueka:tools')
        if task == 'verify-tools':
            call(python, 'scripts/verify_tools.py', *args)
        elif task == 'verify-restore':
            state = manager_state()
            project = state['Config']['Labels']['com.docker.compose.project']
            container = subprocess.check_output(['docker', 'ps', '-q', '--filter', f'label=com.docker.compose.project={project}',
                                                 '--filter', 'label=com.docker.compose.service=postgres-test'], text=True).strip()
            call(python, 'scripts/verify_postgres_restore.py', '--client-container', container, *args)
        elif task == 'verify-caddy':
            state = manager_state()
            network = next(iter(state['NetworkSettings']['Networks']))
            tag = 'tueka-caddy-check:' + uuid.uuid4().hex
            try:
                call('docker', 'build', '-f', 'Dockerfile.caddy-test', '--build-arg', 'APP_IMAGE=' + image, '-t', tag, '.')
                call('docker', 'run', '--rm', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                     '--tmpfs', '/tmp:rw,nosuid,size=256m', '--network', network, '-e',
                     'TUEKA_TEST_DATABASE_URL=' + os.environ['TUEKA_TEST_DATABASE_URL'], tag, *args)
            finally:
                subprocess.run(['docker', 'image', 'rm', tag], stdout=subprocess.DEVNULL)
        else:
            script = 'runtime_image' if task == 'verify-runtime' else task.removeprefix('verify-')
            extra = [] if task == 'verify-setup' else ['--image', image]
            if task == 'verify-runtime':
                extra += ['--network', next(iter(manager_state()['NetworkSettings']['Networks']))]
            call(python, f'scripts/verify_{script}.py', *extra, *args)
            if task == 'verify-runtime':
                call('docker', 'run', '--rm', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                     '--tmpfs', '/tmp:rw,nosuid,size=256m', '--network', extra[-1], '-e',
                     'TUEKA_TEST_DATABASE_URL=' + os.environ['TUEKA_TEST_DATABASE_URL'], image, 'test')
    elif task == 'secrets':
        env = dict(os.environ, GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='safe.directory', GIT_CONFIG_VALUE_0=str(SOURCE))
        call('gitleaks', 'git', str(SOURCE), '--redact', '--log-opts=--all',
             '--gitleaks-ignore-path', str(SOURCE / '.gitleaksignore'), '--report-format', 'json',
             '--report-path', str(Path(os.environ['TUEKA_TASK_OUTPUT']) / 'gitleaks.json'), *args, env=env)
    elif task == 'ci':
        parser = argparse.ArgumentParser()
        parser.add_argument('--group', choices=GROUPS)
        selected = parser.parse_args(args).group
        tasks = GROUPS[selected] if selected else sum(GROUPS.values(), [])
        project = 'tueka-tools-ci-' + uuid.uuid4().hex[:12]
        base = ['docker', 'compose', '--env-file', 'tests/postgres.env', '-p', project, '-f', 'compose.tools.yaml']
        # All tasks use a run-specific image tag and isolated Compose project.
        env = dict(os.environ, TUEKA_TOOLS_IMAGE='tueka-tools-ci:' + project)
        try:
            for child in tasks:
                call(*base, 'run', '--rm', '--build', '-T', '-e', 'TUEKA_TOOLS_IMAGE=' + env['TUEKA_TOOLS_IMAGE'], child, cwd=SOURCE, env=env)
        finally:
            call(*base, 'down', '--remove-orphans', cwd=SOURCE, env=env)
            subprocess.run(['docker', 'image', 'rm', env['TUEKA_TOOLS_IMAGE']], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        raise ValueError('Unknown task: ' + task)


def main():
    if os.environ.get('TUEKA_TOOLS') != '1':
        raise SystemExit('Use docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build <task>.')
    task, *args = sys.argv[1:]
    os.environ.pop('TUEKA_ENV_FILE', None)
    os.environ.pop('DATABASE_URL', None)
    if os.environ.get('TUEKA_HOST_DOCKER_HOST', '').startswith(('tcp:', 'ssh:')):
        raise SystemExit('Remote Docker is unsupported. Select a local Docker Engine or Docker Desktop context.')
    unique = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-') + uuid.uuid4().hex[:8]
    artifacts = SOURCE / 'artifacts' / task / unique
    artifacts.mkdir(parents=True)
    os.environ['TUEKA_TASK_OUTPUT'] = str(artifacts)
    for path in (artifacts.parent.parent, artifacts.parent, artifacts):
        ownership(path)
    direct = task in ('setup', 'deploy', 'recovery', 'check', 'ci', 'secrets') or task.startswith('dev-')
    # Acceptance needs daemon-visible scratch paths; tests use private container /tmp.
    scratch_parent = SOURCE / '.tools-runs' if task.startswith('verify-') else Path('/tmp')
    if task.startswith('dev-'):
        direct = False
    scratch_parent.mkdir(exist_ok=True)
    if scratch_parent.is_relative_to(SOURCE):
        ownership(scratch_parent)
    code = 0
    affected = []
    owners = {}
    parent_owners = {}
    defaults = {}
    if task in ('setup', 'deploy', 'recovery'):
        for index, value in enumerate(args[:-1]):
            if value in ('--config-dir', '--stage-config', '--bundle', '--backup-root', '--output', '--source-config'):
                path = Path(args[index + 1]).resolve()
                affected.append(path)
                ancestor, missing = path, []
                while not ancestor.exists():
                    missing.append(ancestor)
                    ancestor = ancestor.parent
                info = ancestor.stat()
                defaults[path] = (info.st_uid, info.st_gid)
                for parent in missing:
                    parent_owners[parent] = defaults[path]
                for item in ([path, *path.rglob('*')] if path.is_dir() else [path]):
                    if item.exists() and not item.is_symlink():
                        info = item.stat()
                        owners[item] = (info.st_uid, info.st_gid)
    def interrupt(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    with tempfile.TemporaryDirectory(prefix='tueka-', dir=scratch_parent) as scratch:
        root = SOURCE if direct else Path(scratch)
        if not direct:
            copy_source(root)
        try:
            with (artifacts / 'task.log').open('w', encoding='utf-8') as log:
                run(task, args, root, log)
        except subprocess.CalledProcessError as error:
            code = error.returncode if error.returncode > 0 else 1
        except KeyboardInterrupt:
            code = 130
        except Exception as error:
            print(f'{type(error).__name__}: {error}', file=sys.stderr)
            with (artifacts / 'task.log').open('a', encoding='utf-8') as log:
                log.write(f'{type(error).__name__}: {error}\n')
            code = 2
        finally:
            for path in affected:
                for item in ([path, *path.rglob('*')] if path.is_dir() else [path]):
                    if item.exists() and not item.is_symlink():
                        uid, gid = owners.get(item, defaults[path])
                        info = item.stat()
                        if (info.st_uid, info.st_gid) != (uid, gid):
                            os.chown(item, uid, gid)
            for parent, (uid, gid) in parent_owners.items():
                if parent.exists() and not parent.is_symlink():
                    info = parent.stat()
                    if (info.st_uid, info.st_gid) != (uid, gid):
                        os.chown(parent, uid, gid)
            if not direct:
                for relative in ('dashboard/frontend/dist', 'docs/.vitepress/dist',
                                 'dashboard/frontend/test-results', 'dashboard/frontend/playwright-report'):
                    source = root / relative
                    if source.exists():
                        shutil.copytree(source, artifacts / relative, dirs_exist_ok=True)
            result = {'task': task, 'exit_code': code, 'python': sys.version,
                      'locks': {relative: hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest()
                          for relative in ('requirements.lock', 'dashboard/frontend/package-lock.json', 'docs/package-lock.json')}}
            if shutil.which('node'):
                result['node'] = subprocess.check_output(['node', '--version'], text=True).strip()
            (artifacts / 'result.json').write_text(json.dumps(result) + '\n')
            for path in artifacts.rglob('*'):
                ownership(path)
    print(f'{task}: exit={code}; logs: {artifacts.relative_to(SOURCE)}')
    if code:
        print(f'Retry: docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build {task} (with the same arguments)')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
