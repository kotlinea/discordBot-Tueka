"""Validate environment identity before Compose can access persistent volumes."""
import json
import re
import secrets
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from dotenv import dotenv_values

ENVIRONMENTS = ('dev', 'stage', 'prod')
IMMUTABLE_IMAGE = re.compile(r'(?:[a-zA-Z0-9./:_-]+@)?sha256:[0-9a-f]{64}\Z')


def initialize(directory, environment, image, project=None):
    if environment not in ENVIRONMENTS:
        raise ValueError('Unknown environment')
    directory = Path(directory).resolve()
    project = project or 'tueka-' + environment
    validate_identity(environment, image, project)
    directory.mkdir(parents=True, exist_ok=False)
    directory.chmod(0o700)
    password = secrets.token_hex(32)
    metadata = {'environment': environment, 'image': image, 'project': project,
                'dashboard_port': {'dev': 8002, 'stage': 8001, 'prod': 8000}[environment], 'vite_port': 5173}
    (directory / 'deployment.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    values = {
        'TUEKA_ENV': environment,
        'DATABASE_URL': f'postgresql://tueka_{environment}:{quote(password)}@postgres:5432/tueka_{environment}',
        'DISCORD_TOKEN': 'replace-with-dedicated-bot-token',
        'DISCORD_CLIENT_ID': 'replace-with-dedicated-client-id',
        'DISCORD_CLIENT_SECRET': 'replace-with-dedicated-client-secret',
        'SESSION_SECRET': secrets.token_hex(32),
        'MONITORING_TOKEN': secrets.token_hex(32),
        'DISCORD_REDIRECT_URI': ('http://127.0.0.1:5173' if environment == 'dev' else f'https://{environment}.example.invalid') + '/oauth/callback',
        'DASHBOARD_BASE_URL': 'http://127.0.0.1:5173' if environment == 'dev' else f'https://{environment}.example.invalid',
        'DASHBOARD_HTTPS_ONLY': 'false' if environment == 'dev' else 'true',
        'SOCIAL_X_MODE': 'poll',
    }
    for filename, content in (
        ('app.env', ''.join(f'{key}={value}\n' for key, value in values.items())),
        ('database-password', password),
        ('postgres-admin-password', secrets.token_hex(32)),
    ):
        path = directory / filename
        path.write_text(content, encoding='utf-8', newline='\n')
        # Compose file secrets are bind mounts: uid/gid overrides are not portable.
        # The host directory is private, while the mounted file is readable by UID 10001.
        path.chmod(0o644)
    return metadata


def validate_identity(environment, image, project):
    if environment not in ENVIRONMENTS:
        raise ValueError('Unknown environment')
    if not re.fullmatch('tueka-' + environment + r'(?:-[a-z0-9-]+)?', project):
        raise ValueError('Compose project must belong to the selected environment')
    if not image or any(c.isspace() for c in image):
        raise ValueError('Invalid application image')
    if environment != 'dev' and not IMMUTABLE_IMAGE.fullmatch(image):
        raise ValueError('Stage and production require an immutable sha256 image reference')


def read_metadata(directory):
    directory = Path(directory).resolve()
    metadata = json.loads((directory / 'deployment.json').read_text(encoding='utf-8'))
    environment = metadata['environment']
    validate_identity(environment, metadata['image'], metadata['project'])
    for port in ('dashboard_port', 'vite_port'):
        if type(metadata[port]) is not int or not 1024 <= metadata[port] <= 65535:
            raise ValueError('Deployment ports must be integers between 1024 and 65535')
    return metadata


def read(directory, *, require_credentials=True):
    directory = Path(directory).resolve()
    metadata = read_metadata(directory)
    environment = metadata['environment']
    values = dotenv_values(directory / 'app.env', interpolate=False)
    if values.get('TUEKA_ENV') != environment:
        raise ValueError('Secret file belongs to a different environment')
    try:
        url = urlsplit(values.get('DATABASE_URL', ''))
        name = 'tueka_' + environment
        matches = url.scheme == 'postgresql' and url.hostname == 'postgres' and url.port == 5432 and url.path == '/' + name and unquote(url.username or '') == name and not url.query and not url.fragment
        password = (directory / 'database-password').read_bytes().decode('utf-8').rstrip('\n')
        admin = (directory / 'postgres-admin-password').read_bytes().decode('utf-8').rstrip('\n')
        if any(char in password + admin for char in '\r\n'):
            raise ValueError('Database password files must contain one LF-only line')
        matches = matches and password and unquote(url.password or '') == password and admin and admin != password
    except (ValueError, OSError):
        matches = False
    if not matches:
        raise ValueError('Database secrets do not match this environment')
    if require_credentials:
        for key in ('DISCORD_TOKEN', 'DISCORD_CLIENT_ID', 'DISCORD_CLIENT_SECRET', 'SESSION_SECRET'):
            value = values.get(key, '')
            if not value or value.startswith('replace-'):
                raise ValueError('Dedicated Discord and session credentials are required')
        if not str(values['DISCORD_CLIENT_ID']).isdecimal():
            raise ValueError('Discord client ID must be numeric')
        base = urlsplit(values.get('DASHBOARD_BASE_URL', ''))
        callback = values.get('DISCORD_REDIRECT_URI', '')
        if not base.hostname or base.hostname.endswith('.invalid') or base.path not in ('', '/') or callback != values['DASHBOARD_BASE_URL'].rstrip('/') + '/oauth/callback':
            raise ValueError('Dashboard origin and OAuth callback must match')
        if environment != 'dev' and (base.scheme != 'https' or values.get('DASHBOARD_HTTPS_ONLY') != 'true'):
            raise ValueError('Stage and production require HTTPS sessions')
    return metadata, values


def validate_promotion(stage_directory, prod_directory):
    stage, stage_secrets = read(stage_directory)
    prod, prod_secrets = read(prod_directory)
    if stage['environment'] != 'stage' or prod['environment'] != 'prod':
        raise ValueError('Promotion requires stage and prod configurations')
    if stage['image'] != prod['image']:
        raise ValueError('Production must use the exact Stage image digest')
    for key in ('DISCORD_TOKEN', 'DISCORD_CLIENT_ID', 'DISCORD_CLIENT_SECRET', 'SESSION_SECRET', 'DISCORD_REDIRECT_URI'):
        if stage_secrets[key] == prod_secrets[key]:
            raise ValueError('Stage and production credentials and callback must be separate')
