"""Generate public Host Caddy sites from the saved application configuration."""
import ipaddress
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

from .configuration import read


def sites(directories):
    result = []
    domains = set()
    environments = set()
    for directory in directories:
        directory = Path(directory).resolve()
        metadata, values = read(directory, require_credentials=False)
        file = directory / 'app.env'
        if metadata['environment'] not in ('stage', 'prod'):
            raise ValueError(f'{file}: TUEKA_ENV must be stage or prod for Host Caddy; keep Dev on localhost HTTP.')
        if metadata['environment'] in environments:
            raise ValueError(f'{directory / "deployment.json"}: duplicate environment; select at most one Stage and one Prod configuration.')
        origin = values.get('DASHBOARD_BASE_URL') or ''
        try:
            url = urlsplit(origin)
            host = url.hostname or ''
            labels = host.split('.')
            valid = (url.scheme == 'https' and url.port in (None, 443) and url.username is None
                     and url.password is None and url.netloc.lower() in (host, host + ':443')
                     and '?' not in origin and '#' not in origin and url.path in ('', '/')
                     and len(host) <= 253 and len(labels) >= 2
                     and all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels)
                     and not labels[-1].isdigit() and labels[-1] not in ('invalid', 'localhost', 'local')
                     and all(32 < ord(char) < 127 for char in origin))
            try:
                ipaddress.ip_address(host)
                valid = False
            except ValueError:
                pass
        except ValueError:
            valid = False
        if not valid:
            raise ValueError(f'{file}: DASHBOARD_BASE_URL must be an https:// DNS domain origin on port 443, without credentials, query, fragment or path. Set the public Stage/Prod domain; values are not logged.')
        if values.get('DISCORD_REDIRECT_URI') != origin.rstrip('/') + '/oauth/callback':
            raise ValueError(f'{file}: DISCORD_REDIRECT_URI must equal DASHBOARD_BASE_URL (without trailing slash) + /oauth/callback. Register the same URL in Discord Developer Portal.')
        if values.get('DASHBOARD_HTTPS_ONLY') != 'true':
            raise ValueError(f'{file}: set DASHBOARD_HTTPS_ONLY=true for HTTPS sessions.')
        if host in domains:
            raise ValueError(f'{file}: duplicate DASHBOARD_BASE_URL domain. Stage and Prod must use different public domains.')
        domains.add(host)
        environments.add(metadata['environment'])
        result.append((host, metadata['dashboard_port']))
    if not result:
        raise ValueError('Select at least one --config-dir for Stage or Prod.')
    return result


def render(directories):
    blocks = ['# Generated Tueka sites; import this file from the Host Caddyfile.\n# No application secrets or access logging.\n']
    for host, port in sites(directories):
        blocks.append(f'''{host} {{
    @internal path /internal /internal/*
    handle @internal {{
        respond 404
    }}
    handle {{
        reverse_proxy 127.0.0.1:{port}
    }}
}}
''')
    return '\n'.join(blocks)


def generate(directories, output, *, overwrite=False):
    directories = [Path(path).resolve() for path in directories]
    output = Path(output)
    if output.is_symlink() or any(output.resolve().is_relative_to(path) for path in directories):
        raise ValueError(f'{output}: choose an output outside application configuration directories; input settings must not be overwritten.')
    content = render(directories)  # Validate all inputs before creating output.
    output.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite:
        try:
            with output.open('x', encoding='utf-8', newline='\n') as stream:
                stream.write(content)
        except FileExistsError:
            raise ValueError(f'{output}: already exists. Review it and use --overwrite to replace the generated sites file.') from None
    else:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=output.parent, encoding='utf-8', newline='\n', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
            os.replace(temporary, output)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return output.resolve()
