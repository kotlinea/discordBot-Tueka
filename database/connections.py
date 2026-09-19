"""PostgreSQL connections and bounded, process-local pools."""
from __future__ import annotations

import atexit
import hashlib
import os
import time
from collections import OrderedDict
from contextlib import contextmanager
from threading import RLock

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row, tuple_row
from psycopg_pool import ConnectionPool
from observability.metrics import registry

POOL_TIMEOUT = 10
_pools: OrderedDict[str, ConnectionPool] = OrderedDict()
_lock = RLock()


def database_url(value: str | None = None) -> str:
    value = value if value is not None else os.environ.get('DATABASE_URL', '')
    if not isinstance(value, str) or not value.startswith(('postgresql://', 'postgres://')):
        raise ValueError('DATABASE_URL must be a PostgreSQL URL; file databases are unsupported')
    try:
        config = conninfo_to_dict(value)
    except psycopg.ProgrammingError:
        raise ValueError('Invalid DATABASE_URL') from None
    if any(port and (not port.isdecimal() or not 1 <= int(port) <= 65535) for port in config.get('port', '').split(',')):
        raise ValueError('Invalid DATABASE_URL port')
    if not config.get('dbname'):
        raise ValueError('DATABASE_URL must name a database')
    return value


def connect(url: str, *, read_only: bool = False, autocommit: bool = False,
            rows: bool = True) -> psycopg.Connection:
    connection = psycopg.connect(database_url(url), autocommit=autocommit,
        row_factory=dict_row if rows else tuple_row, connect_timeout=10,
        application_name='tueka')
    connection.read_only = read_only
    return connection


def _configure(connection):
    connection.execute("SET statement_timeout = '30s'")
    connection.execute("SET lock_timeout = '10s'")
    connection.execute("SET idle_in_transaction_session_timeout = '30s'")
    connection.execute("SET timezone = 'UTC'")


def pool(url: str) -> ConnectionPool:
    url = database_url(url)
    with _lock:
        existing = _pools.get(url)
        if existing is not None and not existing.closed:
            _pools.move_to_end(url)
            return existing
        if len(_pools) >= 8:
            _, old = _pools.popitem(last=False)
            old.close()
        result = ConnectionPool(url, min_size=0, max_size=4, timeout=POOL_TIMEOUT,
            max_waiting=32, max_idle=60, reconnect_timeout=10, open=True,
            name='tueka-' + hashlib.sha256(url.encode()).hexdigest()[:10],
            kwargs={'autocommit': True, 'row_factory': dict_row, 'connect_timeout': 10,
                    'application_name': 'tueka'}, configure=_configure,
            check=ConnectionPool.check_connection)
        _pools[url] = result
        return result


@contextmanager
def transaction(url: str):
    started = time.monotonic()
    try:
        with pool(url).connection() as connection:
            registry.observe('db_pool_acquire_seconds', time.monotonic() - started)
            with connection.transaction():
                yield connection
    except Exception as error:
        code = getattr(error, 'sqlstate', '')
        category = {'40P01': 'deadlock', '55P03': 'lock_timeout', '57014': 'query_timeout'}.get(code, 'connection' if isinstance(error, psycopg.OperationalError) else 'other')
        registry.add('db_errors_total', category=category)
        raise
    finally:
        registry.observe('db_transaction_seconds', time.monotonic() - started)


def pool_statistics():
    with _lock:
        pools = list(_pools.values())
    names = ('pool_size', 'pool_available', 'requests_waiting', 'requests_queued', 'requests_wait_ms', 'requests_errors', 'connections_errors')
    snapshots = [item.get_stats() for item in pools]
    return {name: sum(snapshot.get(name, 0) for snapshot in snapshots) for name in names}


def lock_resource(connection, namespace: str, key: str | int):
    """Serialize creation/update of an entity whose row may not exist yet."""
    connection.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))',
                       (f'{namespace}:{key}',))


def close_pools(url: str | None = None) -> None:
    with _lock:
        if url is None:
            closing = list(_pools.values())
            _pools.clear()
        else:
            item = _pools.pop(url, None)
            closing = [item] if item else []
    for item in closing:
        item.close()


atexit.register(close_pools)
