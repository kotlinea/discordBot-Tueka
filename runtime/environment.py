"""Load explicit deployment secrets without falling back to a mounted source .env."""
import os
from pathlib import Path

from dotenv import load_dotenv


def load_environment():
    explicit = os.environ.get('TUEKA_ENV_FILE')
    path = Path(explicit) if explicit else Path(__file__).resolve().parents[1] / '.env'
    if explicit and not path.is_file():
        raise RuntimeError('Configured TUEKA_ENV_FILE is unavailable')
    load_dotenv(path, override=False, interpolate=not bool(explicit))
