"""Apply PostgreSQL migrations before starting Bot, Dashboard, or Worker."""
import argparse
import json
import os
import sys
import psycopg
from runtime.environment import load_environment
from observability.logging import configure_logging

from database.migrations import MIGRATIONS, apply, load, statements


def connection_failure(error):
    """Classify libpq failures without emitting credentials or server messages."""
    message = str(error).lower()
    if error.sqlstate == '28P01' or 'password authentication failed' in message:
        return 'database_authentication_failed', 'Restore the app.env DATABASE_URL password and database-password used to initialize this DB. Changing files does not change an existing PostgreSQL role password.'
    if error.sqlstate == '3D000' or ('database ' in message and 'does not exist' in message):
        return 'database_missing', 'Check the DATABASE_URL database and the environment/project that owns the PostgreSQL volume.'
    if 'translate host name' in message or 'name or service not known' in message or 'name resolution' in message:
        return 'database_dns_failed', 'Check DATABASE_URL host postgres and the shared Compose database network.'
    if 'connection refused' in message:
        return 'database_connection_refused', 'Check PostgreSQL is running and DATABASE_URL uses postgres:5432.'
    if 'timeout' in message or 'timed out' in message:
        return 'database_connection_timeout', 'Check PostgreSQL readiness, resource usage and the shared Compose database network.'
    return 'database_connection_failed', 'Check app.env DATABASE_URL, PostgreSQL status and the credentials associated with its existing volume. The failure could not be classified.'


def main():
    configure_logging('migrate')
    load_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', default=os.environ.get('DATABASE_URL'))
    args = parser.parse_args()
    try:
        result = apply(args.database_url)
    except psycopg.OperationalError as error:
        code, action = connection_failure(error)
        print(json.dumps({'event': 'migration_failed', 'code': code, 'action': action}), file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(result))


if __name__ == '__main__':
    main()
