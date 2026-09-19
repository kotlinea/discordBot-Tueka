"""Apply PostgreSQL migrations before starting Bot, Dashboard, or Worker."""
import argparse
import json
import os
from runtime.environment import load_environment
from observability.logging import configure_logging

from database.migrations import MIGRATIONS, apply, load, statements


def main():
    configure_logging('migrate')
    load_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', default=os.environ.get('DATABASE_URL'))
    args = parser.parse_args()
    print(json.dumps(apply(args.database_url)))


if __name__ == '__main__':
    main()
