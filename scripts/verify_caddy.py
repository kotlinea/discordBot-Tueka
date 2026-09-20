"""Offline HTTPS acceptance in Dockerfile.caddy-test; no Host trust changes."""
from contextlib import ExitStack
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from database.testing import temporary_database
from deploy.caddy import render
from deploy.configuration import initialize


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def request(host, number, path, context=None):
    connection = (http.client.HTTPSConnection(host, number, context=context, timeout=5) if context
                  else http.client.HTTPConnection(host, number, timeout=5))
    connection._create_connection = lambda address, *args, **kwargs: socket.create_connection(('127.0.0.1', address[1]), timeout=5)
    try:
        connection.request('GET', path)
        response = connection.getresponse()
        body = response.read()
        return response.status, dict((key.lower(), value) for key, value in response.getheaders()), body
    finally:
        connection.close()


def main():
    processes = []
    with tempfile.TemporaryDirectory(prefix='tueka-caddy-') as scratch, ExitStack() as stack:
        root = Path(scratch)
        try:
            directories = []
            for environment in ('stage', 'prod'):
                directory = root / environment
                initialize(directory, environment, 'sha256:' + 'a' * 64)
                metadata_file = directory / 'deployment.json'
                metadata = json.loads(metadata_file.read_text())
                metadata['dashboard_port'] = port()
                metadata_file.write_text(json.dumps(metadata))
                file = directory / 'app.env'
                text = file.read_text().replace('.example.invalid', '.example.com')
                file.write_text(text)
                directories.append(directory)
                # Only the offline fixture uses an isolated schema on the dedicated test server.
                database = stack.enter_context(temporary_database())
                fixture = directory / 'fixture.env'
                fixture.write_text('\n'.join(line for line in text.splitlines() if not line.startswith('DATABASE_URL=')) + '\nDATABASE_URL=' + database + '\n', encoding='utf-8')
                env = {**os.environ, 'TUEKA_ENV_FILE': str(fixture), 'PYTHONUNBUFFERED': '1'}
                processes.append(subprocess.Popen(['python', '-m', 'uvicorn', 'tests.fixtures.caddy_dashboard:app',
                    '--host', '127.0.0.1', '--port', str(metadata['dashboard_port']), '--no-access-log'], env=env,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            http_port, https_port = port(), port()
            file = root / 'Caddyfile'
            # Production site blocks are unchanged; local-only global options select an internal CA.
            file.write_text(f'{{\n admin off\n skip_install_trust\n local_certs\n http_port {http_port}\n https_port {https_port}\n}}\n' + render(directories))
            env = {**os.environ, 'XDG_DATA_HOME': str(root / 'data'), 'XDG_CONFIG_HOME': str(root / 'config')}
            subprocess.run(['caddy', 'validate', '--config', str(file), '--adapter', 'caddyfile'], env=env, check=True, capture_output=True)
            processes.append(subprocess.Popen(['caddy', 'run', '--config', str(file), '--adapter', 'caddyfile'], env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            deadline = time.monotonic() + 60
            authority = root / 'data/caddy/pki/authorities/local/root.crt'
            while True:
                try:
                    context = ssl.create_default_context(cafile=str(authority))
                    if all(request(f'{name}.example.com', https_port, '/health/ready', context)[0] == 200 for name in ('stage', 'prod')):
                        break
                except (OSError, http.client.HTTPException):
                    pass
                if time.monotonic() >= deadline or any(process.poll() is not None for process in processes):
                    raise RuntimeError('Local Caddy/Dashboard readiness failed (no public ACME was used).')
                time.sleep(0.5)
            for environment in ('stage', 'prod'):
                host = f'{environment}.example.com'
                status, headers, _ = request(host, http_port, '/docs/')
                assert status == 308, (status, headers.get('location'))
                redirect = urlsplit(headers['location'])
                assert redirect.scheme == 'https' and redirect.hostname == host and redirect.path == '/docs/'
                assert redirect.port in (None, 443, https_port)
                for path, expected in (('/docs/', 200), ('/servers', 200), ('/api/v1/session', 401),
                                       ('/api/docs', 404), ('/api/openapi.json', 404), ('/oauth/callback', 400),
                                       ('/internal', 404), ('/internal/metrics', 404)):
                    status, headers, _ = request(host, https_port, path, context)
                    assert status == expected, (environment, path, status)
                    if path.startswith('/internal'):
                        assert 'x-acceptance-environment' not in headers  # Blocked before reaching the app.
                    else:
                        assert headers['x-acceptance-environment'] == environment
                status, headers, _ = request(host, https_port, '/login', context)
                assert status == 303
                target = urlsplit(headers['location'])
                assert target.hostname == 'discord.com'
                assert parse_qs(target.query)['redirect_uri'] == [f'https://{host}/oauth/callback']
                status, headers, _ = request(host, https_port, '/_acceptance/session', context)
                assert status == 200 and 'secure' in headers['set-cookie'].lower()
                status, headers, _ = request(host, https_port, '/webhooks/youtube', context)
                assert status != 404 and headers['x-acceptance-environment'] == environment
            print('Caddy: trusted local TLS, HTTPS redirect, Stage/Prod isolation, Docs/API/OAuth/Webhook routes, internal and API-docs 404: OK')
        finally:
            for process in reversed(processes):
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == '__main__':
    main()
