"""Explicit, transactional numbered SQLite migrations with verified snapshots."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path

from database import backup, connect

MIGRATIONS = Path(__file__).parent / 'migrations'


def load(directory: Path) -> list[tuple[int, str, str, str]]:
    result = []
    for path in sorted(directory.glob('*.sql')):
        match = re.fullmatch(r'(\d{4})_[a-z0-9_]+\.sql', path.name)
        if not match:
            raise ValueError(f'Invalid migration filename: {path.name}')
        sql = path.read_text(encoding='utf-8').replace('\r\n', '\n')
        result.append((int(match[1]), path.name, hashlib.sha256(sql.encode()).hexdigest(), sql))
    if [item[0] for item in result] != list(range(1, len(result) + 1)):
        raise ValueError('Migration numbers must be consecutive starting at 0001')
    return result


def statements(sql: str):
    buffer = ''
    for char in sql:
        buffer += char
        if char == ';' and sqlite3.complete_statement(buffer):
            yield buffer
            buffer = ''
    if buffer.strip():
        # Allow trailing comments but reject incomplete executable SQL.
        remaining = re.sub(r'--[^\n]*|/\*.*?\*/', '', buffer, flags=re.S)
        if remaining.strip():
            raise ValueError('Migration has an unterminated SQL statement')


def prepare_statement(connection: sqlite3.Connection, statement: str) -> str | None:
    """Resolve an explicitly annotated additive column operation before execution."""
    marker = '-- tueka: add-column-if-missing\n'
    stripped = statement.lstrip()
    if not stripped.startswith(marker):
        return statement
    sql = stripped[len(marker):].strip()
    match = re.fullmatch(r'ALTER TABLE ([a-z_][a-z0-9_]*) ADD COLUMN ([a-z_][a-z0-9_]*)\s+(.+);', sql, flags=re.S)
    if not match:
        raise ValueError('add-column-if-missing requires one ALTER TABLE ADD COLUMN statement')
    table, column = match.group(1, 2)
    columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
    if not columns:
        raise ValueError(f'Cannot add a column to missing table: {table}')
    return None if column in columns else sql


def apply(database: Path, backup_dir: Path, directory: Path = MIGRATIONS) -> dict:
    migrations = load(directory)
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(database, create=True, autocommit=True, rows=False)) as connection:
        connection.execute('BEGIN IMMEDIATE')
        try:
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
            applied = connection.execute('SELECT version,name,checksum FROM schema_migrations ORDER BY version').fetchall() if exists else []
            expected = [item[:3] for item in migrations]
            if applied != expected[:len(applied)] or len(applied) > len(expected):
                raise ValueError('Applied migration history differs from migration files')
            pending = migrations[len(applied):]
            if not pending:
                connection.rollback()
                return {'applied': [], 'snapshot': None}
            snapshot = backup_dir / f'{database.name}.{time.time_ns()}.{uuid.uuid4().hex}.sqlite3'
            # A second read-only connection sees the committed pre-migration state while this
            # connection holds the writer lock. No migration writes have occurred yet.
            backup(database, snapshot)
            connection.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY,name TEXT NOT NULL,checksum TEXT NOT NULL,applied_at INTEGER NOT NULL)')
            forbidden = {sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_SAVEPOINT, sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_PRAGMA}
            def authorize(action, arg1, arg2, db_name, trigger):
                return sqlite3.SQLITE_DENY if action in forbidden else sqlite3.SQLITE_OK
            for version, name, checksum, sql in pending:
                for statement in statements(sql):
                    statement = prepare_statement(connection, statement)
                    if statement is None:
                        continue
                    connection.set_authorizer(authorize)
                    try:
                        connection.execute(statement)
                    finally:
                        connection.set_authorizer(None)
                connection.execute('INSERT INTO schema_migrations VALUES(?,?,?,?)', (version, name, checksum, int(time.time())))
            if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise ValueError('Foreign-key verification failed')
            if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise ValueError('Integrity verification failed')
            connection.commit()
            return {'applied': [item[1] for item in pending], 'snapshot': str(snapshot)}
        except BaseException:
            connection.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, type=Path)
    parser.add_argument('--backup-dir', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(apply(args.database, args.backup_dir)))


if __name__ == '__main__':
    main()
