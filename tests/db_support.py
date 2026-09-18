"""Explicit PostgreSQL schema lifecycle for runtime tests."""
from database import require_current
from database.testing import temporary_database


_databases = {}


def prepare_database(label, cleanup):
    """Reuse a test's logical label; explicitly register schema cleanup with its owner."""
    key = str(label)
    if key.startswith(('postgresql://', 'postgres://')):
        require_current(key)
        return key
    if key not in _databases:
        context = temporary_database()
        url = context.__enter__()
        _databases[key] = url

        def close():
            try:
                context.__exit__(None, None, None)
            finally:
                _databases.pop(key, None)

        cleanup(close)
    return _databases[key]


def snapshot(url):
    """Test-only state comparison; never print application rows in CLI output."""
    from psycopg import sql
    from database import connect
    with connect(url, read_only=True) as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        tables = c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema() AND table_type='BASE TABLE' ORDER BY table_name").fetchall()
        return {row['table_name']: sorted((repr(item) for item in c.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(row['table_name'])))), key=str) for row in tables}
