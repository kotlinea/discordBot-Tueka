"""Manage an explicitly selected environment; never deletes persistent volumes."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deploy.configuration import initialize, read
from deploy.compose import execute, up


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('init', 'check', 'up', 'stop', 'status', 'health', 'logs'))
    parser.add_argument('--config-dir', type=Path, required=True)
    parser.add_argument('--environment', choices=('dev', 'stage', 'prod'))
    parser.add_argument('--image', default='tueka:local')
    parser.add_argument('--stage-config', type=Path)
    args = parser.parse_args()
    try:
        if args.action == 'init':
            if not args.environment:
                parser.error('init requires --environment')
            initialize(args.config_dir, args.environment, args.image)
            print('Created dedicated configuration. Set Discord credentials and public origin before up.')
        elif args.action == 'up':
            up(args.config_dir, args.stage_config)
        elif args.action == 'check':
            read(args.config_dir)
            execute(args.config_dir, 'config', '--quiet')
        elif args.action == 'stop':
            execute(args.config_dir, 'stop')
        elif args.action == 'logs':
            execute(args.config_dir, 'logs', '--tail', '100')
        elif args.action == 'health':
            read(args.config_dir)
            execute(args.config_dir, 'run', '--rm', '--no-deps', '--entrypoint', 'python', 'dashboard', '-m', 'observability', 'snapshot')
        else:
            execute(args.config_dir, 'ps')
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__':
    main()
