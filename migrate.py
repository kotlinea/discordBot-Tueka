"""Apply PostgreSQL migrations before starting Bot, Dashboard, or Worker."""
import argparse
import json
import os
from pathlib import Path
from dotenv import load_dotenv

from database.migrations import MIGRATIONS, apply, load, statements


def main():
    load_dotenv(Path(__file__).resolve().parent / '.env')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', default=os.environ.get('DATABASE_URL'))
    args = parser.parse_args()
    print(json.dumps(apply(args.database_url)))


if __name__ == '__main__':
    main()
