"""Container probes and an operator-only database snapshot command."""
import argparse
import json

from runtime.environment import load_environment
from database import database_url
from .heartbeat import local_ready
from .repository import snapshot
from .configuration import thresholds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('probe', 'snapshot'))
    parser.add_argument('service', nargs='?', choices=('bot', 'dashboard', 'social-worker'))
    args = parser.parse_args()
    if args.command == 'probe':
        raise SystemExit(0 if args.service and local_ready(args.service) else 1)
    load_environment()
    try:
        value = snapshot(database_url(), **thresholds())
    except Exception:
        print(json.dumps({'alerts': ['database_unavailable']}))
        raise SystemExit(1) from None
    print(json.dumps(value))
    raise SystemExit(bool(value['alerts']))


if __name__ == '__main__':
    main()
