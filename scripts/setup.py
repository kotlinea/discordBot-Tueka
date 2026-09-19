"""First installation: check -> configure -> build -> start."""
import argparse
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deploy import setup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'configure', 'build', 'start'))
    parser.add_argument('--config-dir', type=Path, required=True)
    parser.add_argument('--environment', choices=('dev', 'stage', 'prod'))
    parser.add_argument('--project')
    parser.add_argument('--stage-config', type=Path)
    args = parser.parse_args()
    try:
        setup.check(args.config_dir)
        if args.action == 'configure':
            if not args.environment:
                parser.error('configure requires --environment')
            setup.configure(args.config_dir, args.environment, args.project)
            print('Edit app.env in the private configuration directory, then run build. Existing values are preserved.')
        elif args.action == 'build':
            setup.build(args.config_dir, stage_directory=args.stage_config)
            print('Image fixed. Next: start (production also requires --stage-config).')
        elif args.action == 'start':
            setup.start(args.config_dir, stage_directory=args.stage_config)
            print('Startup and health checks passed.')
        else:
            print('Prerequisites passed. Next: configure.')
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        # Do not print commands, subprocess output or environment-derived values.
        detail = str(error) if isinstance(error, ValueError) else type(error).__name__
        parser.exit(2, f'{args.action} failed: {detail}. Correct the prerequisite/configuration and retry this step; see handbook/operator/setup.md.\n')


if __name__ == '__main__':
    main()
