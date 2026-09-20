"""Load the selected app.env; never discover a repository .env implicitly."""
import os
from pathlib import Path

from dotenv import load_dotenv


def load_environment():
    explicit = os.environ.get('TUEKA_ENV_FILE')
    if not explicit:
        # Offline tools/tests may provide their own process environment.
        return
    path = Path(explicit)
    if not path.is_file():
        raise RuntimeError('Configured TUEKA_ENV_FILE is unavailable')
    load_dotenv(path, override=True, interpolate=False, encoding='utf-8-sig')
