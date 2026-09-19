"""One-shot recovery storage operations; binary streams never share log output."""
import argparse
import asyncio
import json
import sys

from config import Settings
from .storage import export_blobs, import_blobs, inspect_database, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('inspect', 'export', 'import', 'empty', 'verify', 'localize'))
    args = parser.parse_args()
    try:
        settings = Settings.from_env()
        root = settings.data_dir / 'ticket-transcripts'
        if args.action == 'export':
            export_blobs(settings, sys.stdout.buffer)
        elif args.action == 'import':
            import_blobs(root, sys.stdin.buffer)
        elif args.action == 'empty':
            if root.exists() and any(root.iterdir()):
                raise ValueError('Transcript directory is not empty')
        elif args.action == 'inspect':
            print(json.dumps(inspect_database(settings.database_url)))
        else:
            print(json.dumps(asyncio.run(verify(settings, localize=args.action == 'localize'))))
    except Exception:
        print('Recovery storage operation failed; services must remain stopped.', file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
