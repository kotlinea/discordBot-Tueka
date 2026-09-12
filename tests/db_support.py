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
    """After seeding data/old DDL, mark a synthetic fixture as a preceding version."""
    with closing(sqlite3.connect(path)) as connection:
        connection.execute('DELETE FROM schema_migrations WHERE version>?', (version,))
        connection.commit()
