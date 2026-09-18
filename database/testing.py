"""Explicit, isolated PostgreSQL schemas for tests and contract generation."""
from contextlib import contextmanager
import os
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from .connections import close_pools, connect, database_url


def test_database_url():
    url = database_url(os.environ.get('TUEKA_TEST_DATABASE_URL', ''))
    if not conninfo_to_dict(url)['dbname'].startswith('tueka_test'):
        raise ValueError('Tests require a dedicated database named tueka_test*')
    return url


@contextmanager
def temporary_database(*, migrate: bool = True):
    base = test_database_url()
    name = 'tueka_test_' + uuid.uuid4().hex
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query))
    query['options'] = '-csearch_path=' + name
    url = urlunsplit(parts._replace(query=urlencode(query)))
    with connect(base, autocommit=True) as connection:
        connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name)))
    try:
        if migrate:
            from .migrations import apply
            apply(url)
        yield url
    finally:
        close_pools(url)
        with connect(base, autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(name)))
