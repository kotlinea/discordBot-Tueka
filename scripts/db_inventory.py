"""PostgreSQL metadata inventory and logical backup CLI; no row contents or credentials are printed."""
import argparse
import json
import os
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.operations import backup, inventory, restore


def main():
    from runtime.environment import load_environment
    load_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', default=os.environ.get('DATABASE_URL'))
    parser.add_argument('--output', type=Path, help='New metadata-only JSON file')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--backup', type=Path, help='New custom-format pg_dump artifact')
    actions.add_argument('--restore', type=Path, help='Restore into an empty database with services stopped')
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error('Output already exists')
    if args.output and args.backup and args.output.resolve() == args.backup.resolve():
        parser.error('Metadata output must differ from the backup artifact')
    if args.restore:
        restore(args.restore, args.database_url)
    result = backup(args.database_url, args.backup) if args.backup else inventory(args.database_url)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as file:
            json.dump(result, file, ensure_ascii=False, indent=2)
    print(json.dumps({'backend': 'postgresql', 'tables': len(result['tables'])} if 'tables' in result else result))


if __name__ == '__main__':
    main()
