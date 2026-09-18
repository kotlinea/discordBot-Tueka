"""PostgreSQL metadata inventory and logical backup/restore operations."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from .connections import connect, database_url


def inventory(url: str) -> dict:
    """Count rows in one consistent read-only snapshot without returning row data."""
    with connect(url, read_only=True) as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        rows = c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema() AND table_type='BASE TABLE' ORDER BY table_name").fetchall()
        tables = []
        for row in rows:
            name = row['table_name']
            count = c.execute(sql.SQL('SELECT COUNT(*) AS count FROM {}').format(sql.Identifier(name))).fetchone()['count']
            columns = c.execute("SELECT column_name,data_type,is_nullable FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=%s ORDER BY ordinal_position", (name,)).fetchall()
            tables.append({'name': name, 'rows': count, 'columns': columns})
        return {'backend': 'postgresql', 'tables': tables}


def _environment(url: str) -> tuple[dict, str]:
    config = conninfo_to_dict(database_url(url))
    names = {'dbname': 'PGDATABASE', 'host': 'PGHOST', 'hostaddr': 'PGHOSTADDR', 'port': 'PGPORT',
        'user': 'PGUSER', 'password': 'PGPASSWORD', 'connect_timeout': 'PGCONNECT_TIMEOUT',
        'options': 'PGOPTIONS', 'application_name': 'PGAPPNAME', 'sslmode': 'PGSSLMODE',
        'sslrootcert': 'PGSSLROOTCERT', 'sslcert': 'PGSSLCERT', 'sslkey': 'PGSSLKEY',
        'sslcrl': 'PGSSLCRL', 'sslcrldir': 'PGSSLCRLDIR', 'target_session_attrs': 'PGTARGETSESSIONATTRS',
        'channel_binding': 'PGCHANNELBINDING'}
    if set(config) - names.keys():
        raise ValueError('Backup URL contains unsupported connection options')
    # Do not inherit another database's libpq credentials or session settings.
    env = {key: value for key, value in os.environ.items() if not key.startswith('PG')}
    env.update({names[key]: value for key, value in config.items()})
    env.setdefault('PGCONNECT_TIMEOUT', '10')
    return env, config['dbname']


def backup(url: str, destination: Path, *, executable: str = 'pg_dump') -> dict:
    """Create a custom-format dump; never overwrite an existing artifact."""
    destination = Path(destination)
    env, _ = _environment(url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as output:
        try:
            result = subprocess.run([executable, '--format=custom', '--no-owner', '--no-privileges'],
                env=env, stdout=output, stderr=subprocess.PIPE, check=False, timeout=1800)
            if result.returncode:
                raise RuntimeError('pg_dump failed; inspect PostgreSQL service health and client compatibility')
        except BaseException:
            output.close()
            destination.unlink()
            raise
    return {'backend': 'postgresql', 'bytes': destination.stat().st_size}


def restore(source: Path, url: str, *, executable: str = 'pg_restore') -> None:
    """Restore atomically into a dedicated empty database while services are stopped."""
    env, name = _environment(url)
    with connect(url, read_only=True) as c:
        present = c.execute("SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','v','m','S','f') LIMIT 1").fetchone()
        if present:
            raise ValueError('Restore requires a dedicated empty database')
    with Path(source).open('rb') as data:
        result = subprocess.run([executable, '--exit-on-error', '--single-transaction', '--no-owner', '--no-privileges', '--dbname', name],
            env=env, stdin=data, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False, timeout=1800)
    if result.returncode:
        raise RuntimeError('pg_restore failed; target transaction was rolled back')
