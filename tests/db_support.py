"""Explicit CLI-equivalent database preparation for runtime tests."""
from pathlib import Path
import sqlite3
from contextlib import closing

from migrate import apply


def prepare_database(path):
    path = Path(path)
    apply(path, path.parent / 'migration-backups')
    return path


def set_fixture_version(path, version):
    """Reconstruct pre-outbox fixtures after seeding the domain's old DDL.

    The legacy fixtures retain additive 0007/0008 columns deliberately. Unlike
    those idempotent additions, 0009 introduces a new table: remove it together
    with its history. Actual 0008-to-current preservation is tested separately.
    """
    with closing(sqlite3.connect(path)) as connection:
        if version < 9:
            connection.execute('DROP TABLE IF EXISTS suggestion_outbox')
        connection.execute('DELETE FROM schema_migrations WHERE version>?', (version,))
        connection.commit()
