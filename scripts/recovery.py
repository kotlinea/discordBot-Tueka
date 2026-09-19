"""Offline Compose backup, separate-volume restore, and explicit recovery release."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deploy.recovery import backup, restore, release, abort


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('backup', 'restore', 'release', 'abort'))
    parser.add_argument('--config-dir', type=Path, required=True)
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--backup-root', type=Path)
    parser.add_argument('--resume-source', action='store_true')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--source-config', type=Path)
    source.add_argument('--source-fenced', action='store_true')
    parser.add_argument('--reconciled', action='store_true')
    args = parser.parse_args()
    try:
        if args.action == 'backup':
            if bool(args.bundle) == bool(args.backup_root):
                parser.error('backup requires exactly one of --bundle or --backup-root')
            destination = args.bundle or args.backup_root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8])
            backup(args.config_dir, destination, resume_source=args.resume_source)
            print(json.dumps({'status': 'backed-up', 'bundle': str(destination)}))
        elif args.action == 'restore':
            if not args.bundle:
                parser.error('restore requires --bundle')
            print(json.dumps(restore(args.config_dir, args.bundle, source_directory=args.source_config, source_fenced=args.source_fenced)))
        elif args.action == 'abort':
            if not args.source_config:
                parser.error('abort requires --source-config')
            abort(args.config_dir, args.source_config)
            print(json.dumps({'status': 'target-held-source-released'}))
        else:
            print(json.dumps(release(args.config_dir, reconciled=args.reconciled)))
    except Exception:
        print('Recovery failed. Keep writers stopped and inspect the bundle/hold and service health; no automatic cleanup or restart was performed.', file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
