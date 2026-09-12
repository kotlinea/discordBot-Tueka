"""Offline SQLite backup and metadata inventory; never print row contents."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import backup, identifier, inventory, readonly


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
