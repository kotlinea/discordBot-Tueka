"""Exclusive host-side operations for one saved Compose configuration."""
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def locked(directory):
    path = Path(directory) / '.recovery.lock'
    with path.open('x') as file:
        file.write('Deployment or offline recovery operation in progress\n')
    try:
        yield
    finally:
        path.unlink()
