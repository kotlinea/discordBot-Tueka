"""Shared SQLite connections, transactions, schema gate, and verified backups."""
from __future__ import annotations

import sqlite3
import time
from contextlib import closing, contextmanager
from pathlib import Path

BUSY_TIMEOUT_MS = 10000


class SchemaNotReady(RuntimeError):
    """An explicit migration is required before starting a runtime consumer."""


def connect(path: str | Path, *, create: bool = False, read_only: bool = False,
            autocommit: bool = False, rows: bool = True) -> sqlite3.Connection:
    path = Path(path)
    mode = 'ro' if read_only else ('rwc' if create else 'rw')
    connection = sqlite3.connect(path.resolve().as_uri() + '?mode=' + mode, uri=True,
                                timeout=BUSY_TIMEOUT_MS / 1000,
                                isolation_level=None if autocommit else '')
    try:
        if rows:
            connection.row_factory = sqlite3.Row
        connection.execute(f'PRAGMA busy_timeout={BUSY_TIMEOUT_MS}')
        connection.execute('PRAGMA foreign_keys=ON')
        if not read_only:
            deadline = time.monotonic() + BUSY_TIMEOUT_MS / 1000
            while True:
                try:
                    if connection.execute('PRAGMA journal_mode').fetchone()[0] != 'wal':
                        connection.execute('PRAGMA journal_mode=WAL')
                    break
                except sqlite3.OperationalError as exc:
                    # Concurrent first opens can race while changing the journal mode.
                    if (getattr(exc, 'sqlite_errorcode', 0) & 255) not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED} or time.monotonic() >= deadline:
                        raise
                    time.sleep(0.01)
        return connection
    except BaseException:
        connection.close()
        raise


def readonly(path: Path) -> sqlite3.Connection:
    return connect(path, read_only=True, rows=False)


@contextmanager
def transaction(path: str | Path):
    connection = connect(path)
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def require_current(path: str | Path) -> None:
    # Import lazily: migrate itself uses the connection and backup functions here.
    from migrate import load, MIGRATIONS
    expected = [entry[:3] for entry in load(MIGRATIONS)]
    try:
        with closing(readonly(Path(path))) as connection:
            actual = connection.execute('SELECT version,name,checksum FROM schema_migrations ORDER BY version').fetchall()
    except sqlite3.Error as exc:
        raise SchemaNotReady(f'Database schema is unavailable: {path}. Stop services and apply migrate.py first.') from exc
    if actual != expected:
        raise SchemaNotReady(f'Database schema is not current: {path}. Stop services and apply migrate.py first.')


def identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def inventory(path: Path) -> dict:
    with closing(readonly(path)) as connection:
        connection.execute('BEGIN')
        integrity = [row[0] for row in connection.execute('PRAGMA integrity_check')]
        # Foreign-key diagnostics may contain row IDs. Only return their count.
        violations = sum(1 for _ in connection.execute('PRAGMA foreign_key_check'))
        tables = []
        for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            quoted = identifier(name)
            columns = [{'name': row[1], 'type': row[2], 'not_null': bool(row[3]), 'primary_key': row[5]}
                       for row in connection.execute(f'PRAGMA table_info({quoted})')]
            foreign_keys = [{'table': row[2], 'from': row[3], 'to': row[4], 'on_update': row[5], 'on_delete': row[6]}
                            for row in connection.execute(f'PRAGMA foreign_key_list({quoted})')]
            indexes = [{'name': row[1], 'unique': bool(row[2])}
                       for row in connection.execute(f'PRAGMA index_list({quoted})')]
            tables.append({'name': name, 'rows': connection.execute(f'SELECT COUNT(*) FROM {quoted}').fetchone()[0],
                           'columns': columns, 'foreign_keys': foreign_keys, 'indexes': indexes})
        return {'integrity_ok': integrity == ['ok'], 'foreign_key_violations': violations,
                'user_version': connection.execute('PRAGMA user_version').fetchone()[0], 'tables': tables}


def backup(source: Path, destination: Path) -> dict:
    if source.resolve() == destination.resolve():
        raise ValueError('Source and destination must differ')
    # Open source before creating anything: a missing database must never become an empty database.
    with closing(readonly(source)) as original:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb'):
            pass
        try:
            with closing(sqlite3.connect(destination)) as copied:
                original.backup(copied)
            result = inventory(destination)
            if not result['integrity_ok'] or result['foreign_key_violations']:
                raise ValueError('Snapshot failed integrity or foreign-key verification')
            return result
        except BaseException:
            destination.unlink(missing_ok=True)
            raise


