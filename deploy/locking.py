"""Exclusive host-side operations for one saved Compose configuration."""
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def locked(directory):
    path = Path(directory) / '.recovery.lock'
    try:
        file = path.open('x')
    except FileExistsError:
        raise ValueError(
            f'Operation lock already exists: {path.resolve()}. '
            'Another setup/deploy/recovery operation may be running, or a previous operation was interrupted. '
            'Wait for the active operation to finish. If none is running, inspect recovery-pending.json and '
            'recovery-fence.json and follow handbook/operator/setup.md before removing this lock. '
            'Existing configuration has been preserved.'
        ) from None
    try:
        with file:
            file.write('Deployment or offline recovery operation in progress\n')
        yield
    finally:
        path.unlink()
