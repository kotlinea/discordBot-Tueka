"""Opt-in local backups and optional SMTP notifications for the operator CLI."""
from contextlib import contextmanager
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
import json
import os
from pathlib import Path
import shutil
import smtplib
import ssl
import uuid

from .configuration import read, read_metadata
from .compose import APPLICATIONS
from .docker_bridge import daemon_path, inspect_self
from .recovery import backup, running


class BackupJobError(RuntimeError):
    """A safe operator-facing error; never includes configuration values."""


class BackupConfigurationError(ValueError):
    """Only fixed validation messages, never supplied configuration values."""


def _object(value, fields):
    if not isinstance(value, dict) or set(value) - set(fields):
        raise BackupConfigurationError('Unknown or invalid backup configuration fields')
    return value


def _boolean(value):
    if type(value) is not bool:
        raise BackupConfigurationError('Backup flags must be JSON booleans')
    return value


def _integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise BackupConfigurationError('Invalid backup numeric setting')
    return value


def _text(value, *, empty=False):
    if not isinstance(value, str) or any(character in value for character in ('\r', '\n', '\0')) or (not empty and not value.strip()):
        raise BackupConfigurationError('Invalid backup text setting')
    return value


def _smtp(value, config_file):
    value = _object(value, ('enabled', 'host', 'port', 'tls', 'username', 'password', 'from', 'to',
                            'on_success', 'timeout_seconds'))
    if not _boolean(value.get('enabled', False)):
        return None
    if os.name == 'posix' and config_file.stat().st_mode & 0o077:
        raise BackupConfigurationError('SMTP configuration requires a private configuration file (mode 0600)')
    result = dict(value)
    for field in ('host', 'from'):
        _text(result.get(field))
    if len(result['host']) > 253 or any(character.isspace() or character in '/@?#' for character in result['host']):
        raise BackupConfigurationError('SMTP host must be a hostname or IP address')
    for field in ('username', 'password'):
        result[field] = _text(result.get(field, ''), empty=True)
    if bool(result['username']) != bool(result['password']):
        raise BackupConfigurationError('SMTP authentication requires both username and password')
    result['port'] = _integer(result.get('port', 465), 1, 65535)
    result['timeout_seconds'] = _integer(result.get('timeout_seconds', 15), 1, 60)
    result['on_success'] = _boolean(result.get('on_success', False))
    if result.get('tls') not in ('ssl', 'starttls'):
        raise BackupConfigurationError('SMTP requires SSL or STARTTLS')
    recipients = result.get('to')
    if not isinstance(recipients, list) or not recipients or len(recipients) > 20:
        raise BackupConfigurationError('SMTP requires recipient addresses')
    for address in [result['from'], *recipients]:
        _text(address)
        if parseaddr(address)[1] != address or '@' not in address:
            raise BackupConfigurationError('SMTP requires bare email addresses')
    return result


def load_options(config_file):
    config_file = Path(config_file).resolve()
    if config_file.stat().st_size > 1024 * 1024:
        raise BackupConfigurationError('Backup configuration is too large')
    try:
        document = json.loads(config_file.read_text(encoding='utf-8-sig'))
    except (ValueError, UnicodeError):
        raise BackupConfigurationError('Invalid JSON backup configuration') from None
    value = _object(document,
                    ('version', 'enabled', 'environments', 'minimum_free_gib', 'smtp'))
    if type(value.get('version')) is not int or value['version'] != 1:
        raise BackupConfigurationError('Unsupported backup configuration version')
    if not _boolean(value.get('enabled', False)):
        return None
    entries = value.get('environments')
    if not isinstance(entries, list) or not entries or len(entries) > 20:
        raise BackupConfigurationError('Backup requires environment entries')
    environments = []
    for entry in entries:
        entry = _object(entry, ('config_dir', 'backup_root'))
        directory = (config_file.parent / _text(entry.get('config_dir'))).resolve()
        destination = (config_file.parent / _text(entry.get('backup_root'))).resolve()
        if destination == Path(destination.anchor):
            raise BackupConfigurationError('Backup requires a dedicated output directory')
        environments.append((directory, destination))
    if len({directory for directory, _ in environments}) != len(environments):
        raise BackupConfigurationError('Duplicate backup environment')
    for _, destination in environments:
        if any(destination.is_relative_to(directory) or directory.is_relative_to(destination)
               for directory, _ in environments):
            raise BackupConfigurationError('Backup output must be separate from environment configuration')
        if destination.exists() and not destination.is_dir():
            raise BackupConfigurationError('Backup output must be a directory')
        ancestor = destination
        while not ancestor.exists():
            ancestor = ancestor.parent
        if not ancestor.is_dir():
            raise BackupConfigurationError('Backup output parent must be a directory')
    minimum = _integer(value.get('minimum_free_gib', 5), 1, 1024)
    return environments, minimum, _smtp(value.get('smtp', {'enabled': False}), config_file)


@contextmanager
def _job_lock(config_file):
    path = config_file.with_name(config_file.name + '.lock')
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        yield False
        return
    try:
        os.close(descriptor)
        yield True
    finally:
        path.unlink()


def _notify(options, outcome):
    message = EmailMessage()
    message['Subject'] = 'Tueka backup ' + outcome
    message['From'] = options['from']
    message['To'] = ', '.join(options['to'])
    # No dump, attachment, credential, private path or upstream exception is sent.
    message.set_content('Tueka backup ' + outcome + '. Review the local backup/service log for details.')
    context = ssl.create_default_context()
    factory = smtplib.SMTP_SSL if options['tls'] == 'ssl' else smtplib.SMTP
    kwargs = {'host': options['host'], 'port': options['port'], 'timeout': options['timeout_seconds']}
    if options['tls'] == 'ssl':
        kwargs['context'] = context
    with factory(**kwargs) as client:
        if options['tls'] == 'starttls':
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
        if options['username']:
            client.login(options['username'], options['password'])
        client.send_message(message)


def _restore_owner(path, reference):
    if os.name != 'posix' or os.geteuid() != 0:
        return
    owner = reference.stat()
    for item in [path, *path.rglob('*')]:
        if not item.is_symlink():
            os.chown(item, owner.st_uid, owner.st_gid)


def _create_output(destination, reference):
    missing, ancestor = [], destination
    while not ancestor.exists():
        missing.append(ancestor)
        ancestor = ancestor.parent
    for path in reversed(missing):
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            if not path.is_dir():
                raise BackupConfigurationError('Backup output must be a directory') from None
        else:
            _restore_owner(path, reference)


def _validate_mounts(config_file, environments):
    if os.environ.get('TUEKA_DOCKER_MANAGER') != '1':
        return
    mounts = inspect_self()['Mounts']
    paths = [config_file.parent, *(path for entry in environments for path in entry)]
    for path in paths:
        try:
            daemon_path(path, mounts)
            mount = next(item for item in sorted(mounts, key=lambda item: len(item['Destination']), reverse=True)
                         if path.is_relative_to(Path(item['Destination']).resolve()))
            if not mount.get('RW'):
                raise ValueError('Read-only mount')
        except ValueError:
            raise BackupConfigurationError('Backup paths require writable bind directories; add an explicit tools volume mount') from None


def _active_environments(environments, minimum_free_gib):
    # Validate every configured environment before any writer is stopped.
    active, projects, applications = [], set(), set()
    for directory, destination in environments:
        metadata = read_metadata(directory)
        if metadata['environment'] not in ('stage', 'prod') or metadata['project'] in projects:
            raise BackupConfigurationError('Backup requires distinct immutable Stage/Prod projects')
        projects.add(metadata['project'])
        services = running(directory)
        if not services:
            continue
        if any((directory / marker).exists() for marker in ('.recovery.lock', 'recovery-pending.json', 'recovery-fence.json')):
            raise BackupConfigurationError('Backup refused an active deployment/recovery operation')
        _, values = read(directory)
        if services != set(APPLICATIONS):
            raise BackupConfigurationError('Backup refused a partially running environment')
        if values['DISCORD_CLIENT_ID'] in applications:
            raise BackupConfigurationError('Backup refused simultaneously running projects with the same Discord Application')
        applications.add(values['DISCORD_CLIENT_ID'])
        ancestor = destination
        while not ancestor.exists():
            ancestor = ancestor.parent
        if shutil.disk_usage(ancestor).free < minimum_free_gib * 1024**3:
            raise BackupConfigurationError('Insufficient free space for backup')
        active.append((directory, destination))
    return active


def run(config_file):
    config_file = Path(config_file).resolve()
    options = load_options(config_file)
    if options is None:
        return {'status': 'disabled'}
    environments, minimum_free_gib, smtp = options
    _validate_mounts(config_file, environments)
    with _job_lock(config_file) as acquired:
        if not acquired:
            return {'status': 'busy'}
        try:
            active = _active_environments(environments, minimum_free_gib)
        except Exception:
            if smtp:
                try:
                    _notify(smtp, 'failed')
                except Exception:
                    raise BackupJobError('Backup preflight and SMTP notification failed') from None
            raise
        if not active:
            return {'status': 'stopped'}
        bundles = []
        try:
            for directory, destination in active:
                _create_output(destination, config_file)
                bundle = destination / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8])
                try:
                    backup(directory, bundle, resume_source=True)
                finally:
                    if bundle.exists():
                        _restore_owner(bundle, config_file)
                bundles.append(str(bundle))
        except Exception:
            if smtp:
                try:
                    _notify(smtp, 'failed')
                except Exception:
                    raise BackupJobError('Backup and SMTP notification failed; inspect local recovery/service logs') from None
            raise BackupJobError('Backup failed; inspect local recovery/service logs and source health') from None
        if smtp and smtp['on_success']:
            try:
                _notify(smtp, 'completed')
            except Exception:
                raise BackupJobError('Backup completed, but SMTP notification failed') from None
        return {'status': 'backed-up', 'bundles': bundles}
