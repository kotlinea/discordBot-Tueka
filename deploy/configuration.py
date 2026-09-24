"""Validate environment identity before Compose can access persistent volumes."""
import json
import re
import secrets
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from dotenv import dotenv_values
from . import env_template

ENVIRONMENTS = ('dev', 'stage', 'prod')
IMMUTABLE_IMAGE = re.compile(r'(?:[a-zA-Z0-9./:_-]+@)?sha256:[0-9a-f]{64}\Z')


def initialize(directory, environment, image, project=None, *, draft=False, existing_empty=False):
    if environment not in ENVIRONMENTS:
        raise ValueError('Unknown environment')
    directory = Path(directory).resolve()
    project = project or 'tueka-' + environment
    validate_identity(environment, ('sha256:' + '0' * 64) if draft else image, project)
    if existing_empty:
        if any(path.name != '.recovery.lock' for path in directory.iterdir()):
            raise ValueError(f'Configuration directory is not empty: {directory}. Existing files were preserved.')
    else:
        directory.mkdir(parents=True, exist_ok=False)
    directory.chmod(0o700)
    password = secrets.token_hex(32)
    metadata = {'environment': environment, 'image': None if draft else image, 'project': project,
                'dashboard_port': {'dev': 8002, 'stage': 8001, 'prod': 8000}[environment], 'vite_port': 5173}
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
        ('app.env', env_template.render({**env_template.defaults(environment, password), **values})),
        ('database-password', password),
        ('postgres-admin-password', secrets.token_hex(32)),
    ):
        path = directory / filename
        path.write_text(content, encoding='utf-8', newline='\n')
        # Compose file secrets are bind mounts: uid/gid overrides are not portable.
        # The host directory is private, while the mounted file is readable by UID 10001.
        path.chmod(0o644)
    # Metadata marks a complete configuration; publish it after every secret exists.
    (directory / ('setup.json' if draft else 'deployment.json')).write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
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


def read_metadata(directory, *, draft=False):
    directory = Path(directory).resolve()
    metadata = json.loads((directory / ('setup.json' if draft else 'deployment.json')).read_text(encoding='utf-8'))
    environment = metadata['environment']
    validate_identity(environment, ('sha256:' + '0' * 64) if draft else metadata['image'], metadata['project'])
    for port in ('dashboard_port', 'vite_port'):
        if type(metadata[port]) is not int or not 1024 <= metadata[port] <= 65535:
            raise ValueError('Deployment ports must be integers between 1024 and 65535')
    return metadata


def read(directory, *, require_credentials=True, draft=False):
    directory = Path(directory).resolve()
    metadata = read_metadata(directory, draft=draft)
    app_file = directory / 'app.env'
    if not app_file.is_file():
        raise ValueError(f'{app_file}: app.env is missing. Select the intended --config-dir or restore this environment configuration; do not copy another environment file.')
    values = dotenv_values(app_file, interpolate=False, encoding='utf-8-sig')
    return validate_values(directory, metadata, values, require_credentials=require_credentials, draft=draft)


def validate_values(directory, metadata, values, *, require_credentials=True, draft=False):
    environment = metadata['environment']
    app_file = directory / 'app.env'
    metadata_file = directory / ('setup.json' if draft else 'deployment.json')
    if values.get('TUEKA_ENV') != environment:
        actual = values.get('TUEKA_ENV')
        actual_label = actual if actual in ENVIRONMENTS else ('<missing or empty>' if not actual else '<invalid value; expected dev/stage/prod>')
        raise ValueError(
            f'Secret file belongs to a different environment.\n'
            f'File: {app_file}\n'
            f'Field: TUEKA_ENV\n'
            f'Actual: {actual_label}\nExpected: {environment} (from {metadata_file}, field environment)\n'
            f'Fix: If this is the intended environment, edit {app_file} and set TUEKA_ENV={environment}. '
            f'If you intended another environment, retry with its --config-dir instead. '
            f'Do not change metadata environment or copy another environment secrets merely to bypass this check.'
        )
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
        raise ValueError(
            f'Database secrets do not match this environment. File: {app_file}; field: DATABASE_URL. '
            f'Expected: postgresql scheme, host postgres, port 5432, user/database tueka_{environment}, no query/fragment. '
            f'The URL password must match {directory / "database-password"}; '
            f'{directory / "postgres-admin-password"} must contain a different nonempty password. '
            f'Password files must contain a single LF-only line. Compare these files locally; values are not logged. '
            f'Restore the matching configuration for this environment; do not regenerate passwords for an existing DB.'
        )
    if require_credentials:
        for key in ('DISCORD_TOKEN', 'DISCORD_CLIENT_ID', 'DISCORD_CLIENT_SECRET', 'SESSION_SECRET'):
            value = values.get(key, '')
            if not value or value.startswith('replace-'):
                raise ValueError(f'{app_file}: {key} is missing, empty or a placeholder. Set {key} to this environment dedicated value in a local editor; its value is not logged.')
        if not str(values['DISCORD_CLIENT_ID']).isdecimal():
            raise ValueError(f'{app_file}: DISCORD_CLIENT_ID must be numeric. Enter the Application ID from Discord Developer Portal; do not use a Bot Token or Client Secret.')
        base = urlsplit(values.get('DASHBOARD_BASE_URL', ''))
        callback = values.get('DISCORD_REDIRECT_URI', '')
        if not base.hostname or base.hostname.endswith('.invalid') or base.path not in ('', '/') or callback != values['DASHBOARD_BASE_URL'].rstrip('/') + '/oauth/callback':
            raise ValueError(f'{app_file}: DASHBOARD_BASE_URL / DISCORD_REDIRECT_URI do not match. Set DASHBOARD_BASE_URL to the public origin (scheme and host, no path; not .invalid), and DISCORD_REDIRECT_URI to that origin plus /oauth/callback. Register the same callback in Discord Developer Portal. Values are not logged.')
        if environment != 'dev' and (base.scheme != 'https' or values.get('DASHBOARD_HTTPS_ONLY') != 'true'):
            raise ValueError(f'{app_file}: Stage and production require HTTPS sessions. Set DASHBOARD_BASE_URL to an https:// origin, DISCORD_REDIRECT_URI to the same origin plus /oauth/callback, and DASHBOARD_HTTPS_ONLY=true.')
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
