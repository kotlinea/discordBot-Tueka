"""Archive encrypted blobs and prove that restored keys decrypt stored content."""
import asyncio
import hashlib
import gzip
import json
from pathlib import Path, PurePosixPath
import tarfile
import io

from database import connect, require_current, transaction
from jobs.catalog import QUEUE_SPECS
from social.crypto import SocialTokenCipher
from ticketing.transcripts import TranscriptStorage


def storage(settings):
    return TranscriptStorage(settings.data_dir / 'ticket-transcripts', settings.ticket_encryption_key,
        s3={name: getattr(settings, 'ticket_s3_' + name) for name in
            ('endpoint_url', 'region', 'bucket', 'access_key_id', 'secret_access_key', 'prefix')})


def references(url):
    with connect(url, read_only=True) as c:
        return [(table, row) for table in ('ticket_transcripts', 'ticket_attachments')
                for row in c.execute(f"SELECT id,backend,object_key,content_hash FROM {table} WHERE status='ready' ORDER BY id")]


def key_generations(values):
    return {name: hashlib.sha256(values[name].encode()).hexdigest() if values.get(name) else None
            for name in ('TICKET_ENCRYPTION_KEY', 'SOCIAL_TOKEN_ENCRYPTION_KEY')}


def inspect_database(url):
    require_current(url)
    with connect(url, read_only=True) as c:
        migrations = c.execute('SELECT version,name,checksum FROM schema_migrations ORDER BY version').fetchall()
        queues = {name: [dict(row) for row in c.execute(
            f'SELECT {spec.state} AS state,COUNT(*) AS count FROM {name} GROUP BY {spec.state} ORDER BY {spec.state}')]
            for name, spec in QUEUE_SPECS.items()}
    return {'migrations': migrations, 'queues': queues, 'blob_references': len(references(url))}


def export_blobs(settings, output):
    store = storage(settings)
    seen = {}
    with tarfile.open(fileobj=output, mode='w|') as archive:
        for table, row in references(settings.database_url):
            key = row['object_key']
            store._local_path(key)  # Validate even S3 object keys before archiving.
            if key in seen:
                if seen[key] != row['content_hash']:
                    raise ValueError('Conflicting blob references')
                continue
            # Capture S3 objects themselves; do not silently claim a missing remote object was backed up.
            encrypted = store._download_s3(key) if row['backend'] == 's3' else store._local_path(key).read_bytes()
            if store._cipher is None:
                raise ValueError('Transcript encryption key is required')
            plain = store._cipher.decrypt(encrypted)
            if table == 'ticket_transcripts':
                plain = gzip.decompress(plain)
            if hashlib.sha256(plain).hexdigest() != row['content_hash']:
                raise ValueError('Snapshot blob hash mismatch')
            info = tarfile.TarInfo(key)
            info.size, info.mode = len(encrypted), 0o600
            archive.addfile(info, io.BytesIO(encrypted))
            seen[key] = row['content_hash']


def import_blobs(root, source):
    root = Path(root)
    if root.exists() and any(root.iterdir()):
        raise ValueError('Restore requires an empty transcript directory')
    root.mkdir(parents=True, exist_ok=True)
    seen = set()
    with tarfile.open(fileobj=source, mode='r|*') as archive:
        for member in archive:
            relative = PurePosixPath(member.name)
            if not member.isfile() or relative.is_absolute() or '..' in relative.parts or '\\' in member.name or ':' in member.name or member.name in seen:
                raise ValueError('Unsafe or duplicate archive member')
            path = root.joinpath(*relative.parts).resolve()
            if root.resolve() not in path.parents:
                raise ValueError('Archive path escapes transcript directory')
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as output, archive.extractfile(member) as content:
                import shutil
                shutil.copyfileobj(content, output)
            path.chmod(0o600)
            seen.add(member.name)


async def verify(settings, *, localize=False):
    """Verify every live blob and encrypted DB value without exposing plaintext."""
    require_current(settings.database_url)
    store = storage(settings)
    refs = references(settings.database_url)
    for table, row in refs:
        method = store.load if table == 'ticket_transcripts' else store.load_attachment
        await method('local' if localize else row['backend'], row['object_key'], row['content_hash'])
    checked = 0
    with connect(settings.database_url, read_only=True) as c:
        for table, column, mapping in (
            ('ticket_messages', 'encrypted_content', False), ('ticket_feedback', 'comment_encrypted', False),
            ('ticket_feedback', 'answers_encrypted_json', True), ('tickets_v2', 'form_answers_json', True)):
            for row in c.execute(f'SELECT {column} AS value FROM {table}'):
                values = json.loads(row['value'] or '{}').values() if mapping else [row['value']]
                for value in values:
                    if value:
                        store.decrypt_text(value)
                        checked += 1
        cipher = SocialTokenCipher(settings.social_token_encryption_key)
        for row in c.execute('SELECT access_token_encrypted,refresh_token_encrypted FROM social_connections'):
            for value in row.values():
                if value:
                    cipher.decrypt(value)
                    checked += 1
    if localize:
        # Restored objects live in the new Volume. Never write to or delete source S3 objects.
        with transaction(settings.database_url) as c:
            for table in ('ticket_transcripts', 'ticket_attachments'):
                c.execute(f"UPDATE {table} SET backend='local' WHERE status='ready'")
            c.execute('DELETE FROM runtime_heartbeats')
    return {'verified_blobs': len(refs), 'verified_encrypted_values': checked, **inspect_database(settings.database_url)}
