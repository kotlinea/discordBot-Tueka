"""Atomic numbered PostgreSQL migrations, serialized per database/schema."""
from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

import psycopg

from .connections import connect, database_url

MIGRATIONS = Path(__file__).resolve().parents[1] / 'migrations' / 'postgresql'


class SchemaNotReady(RuntimeError):
    """A matching, explicitly applied schema is required by every repository."""


def load(directory: Path = MIGRATIONS) -> list[tuple[int, str, str, str]]:
    result = []
    for path in sorted(directory.glob('*.sql')):
        match = re.fullmatch(r'(\d{4})_[a-z0-9_]+\.sql', path.name)
        if not match:
            raise ValueError(f'Invalid migration filename: {path.name}')
        source = path.read_text(encoding='utf-8').replace('\r\n', '\n')
        result.append((int(match[1]), path.name, hashlib.sha256(source.encode()).hexdigest(), source))
    if not result or [row[0] for row in result] != list(range(1, len(result) + 1)):
        raise ValueError('Migration numbers must be consecutive starting at 0001')
    return result


def statements(source: str):
    """Split plain DDL/DML. Procedural bodies and transaction control are unsupported."""
    tokens = re.compile(r"--[^\n]*|/\*.*?\*/|'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|;|[^;'\"/-]+|.", re.S)
    buffer = ''
    for match in tokens.finditer(source):
        token = match[0]
        if token.startswith(('--', '/*')):
            buffer += ' '
        elif token == ';':
            if buffer.strip():
                first = buffer.lstrip().split(None, 1)[0].upper()
                if first not in {'CREATE', 'ALTER', 'DROP', 'INSERT', 'UPDATE', 'DELETE', 'COMMENT', 'GRANT', 'REVOKE'}:
                    raise ValueError('Migration must not control transactions or sessions')
                yield buffer
            buffer = ''
        else:
            buffer += token
    if buffer.strip():
        raise ValueError('Migration has an unterminated SQL statement')


def require_current(url: str) -> None:
    expected = [row[:3] for row in load()]
    try:
        with connect(url, read_only=True, rows=False) as connection:
            actual = connection.execute('SELECT version,name,checksum FROM schema_migrations ORDER BY version').fetchall()
    except psycopg.Error:
        raise SchemaNotReady('Database schema is unavailable. Apply migrate.py before starting services.') from None
    if actual != expected:
        raise SchemaNotReady('Database schema is not current. Apply migrate.py before starting services.')


def apply(url: str, directory: Path = MIGRATIONS) -> dict:
    migrations = load(directory)
    with connect(database_url(url), rows=False) as connection:
        locked = connection.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(current_database() || ':' || current_schema() || ':tueka-migrate', 0))").fetchone()[0]
        if not locked:
            raise RuntimeError('Another migration is running for this database/schema')
        exists = connection.execute("SELECT to_regclass('schema_migrations')").fetchone()[0]
        applied = connection.execute('SELECT version,name,checksum FROM schema_migrations ORDER BY version').fetchall() if exists else []
        expected = [row[:3] for row in migrations]
        if applied != expected[:len(applied)] or len(applied) > len(expected):
            raise ValueError('Applied migration history differs from migration files')
        pending = migrations[len(applied):]
        if not pending:
            return {'applied': []}
        connection.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY,name TEXT NOT NULL,checksum TEXT NOT NULL,applied_at BIGINT NOT NULL)')
        for version, name, checksum, source in pending:
            for statement in statements(source):
                connection.execute(statement)
            connection.execute('INSERT INTO schema_migrations VALUES(%s,%s,%s,%s)', (version, name, checksum, int(time.time())))
        return {'applied': [row[1] for row in pending]}
