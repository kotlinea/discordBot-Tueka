"""Offline SQLite backup and metadata inventory; never print row contents."""
from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path


def readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--backup', type=Path, help='New snapshot path; existing files are never overwritten')
    parser.add_argument('--output', type=Path, required=True, help='Metadata-only JSON; must not already exist')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists')
    if args.output.resolve() in {args.source.resolve(), args.backup.resolve() if args.backup else args.source.resolve()}:
        parser.error('Metadata output must differ from database paths')
    result = backup(args.source, args.backup) if args.backup else inventory(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    print(json.dumps({'tables': len(result['tables']), 'rows': sum(table['rows'] for table in result['tables']),
                      'integrity_ok': result['integrity_ok'], 'foreign_key_violations': result['foreign_key_violations']}))


if __name__ == '__main__':
    main()
