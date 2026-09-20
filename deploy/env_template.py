"""One catalog for initial app.env files and additive configuration upgrades."""
import io
import os
from pathlib import Path
import stat
import tempfile
from urllib.parse import quote

from dotenv.parser import parse_stream

TEMPLATE = Path(__file__).with_name('app.env.example')


def parse(text, path):
    values = {}
    for binding in parse_stream(io.StringIO(text)):
        if binding.error:
            raise ValueError(f'{path}: invalid app.env syntax at line {binding.original.line}; fix it locally before configure. Values are not logged.')
        if binding.key is not None:
            if binding.key in values:
                raise ValueError(f'{path}: duplicate assignment at line {binding.original.line}; keep one assignment per key before configure. Values are not logged.')
            values[binding.key] = binding.value
    return values


def defaults(environment, password):
    values = parse(TEMPLATE.read_text(encoding='utf-8'), TEMPLATE)
    origin = 'http://127.0.0.1:5173' if environment == 'dev' else f'https://{environment}.example.invalid'
    values.update(TUEKA_ENV=environment,
                  DATABASE_URL=f'postgresql://tueka_{environment}:{quote(password, safe="")}@postgres:5432/tueka_{environment}',
                  DISCORD_REDIRECT_URI=origin + '/oauth/callback', DASHBOARD_BASE_URL=origin,
                  DASHBOARD_HTTPS_ONLY='false' if environment == 'dev' else 'true')
    return values


def render(values, include=None):
    lines = []
    for line in TEMPLATE.read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#'):
            key = line.split('=', 1)[0]
            if include is None or key in include:
                lines.append(f'{key}={values[key] or ""}')
        else:
            lines.append(line)
    return '\n'.join(lines) + '\n'


def append_missing(path, original, addition):
    """Replace atomically while retaining existing bytes and file permissions."""
    newline = b'\r\n' if b'\r\n' in original else b'\n'
    separator = b'' if not original or original.endswith(b'\n') else newline
    content = original + separator + newline + addition.replace('\n', newline.decode()).encode('utf-8')
    mode = stat.S_IMODE(path.stat().st_mode)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.app-env-', delete=False) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != original:
            raise ValueError(f'{path}: changed during configure; retry after editing is complete.')
        if os.name == 'nt':
            # ReplaceFile retains the destination's Windows ACL, unlike rename.
            import ctypes
            from ctypes import wintypes
            replace = ctypes.WinDLL('kernel32', use_last_error=True).ReplaceFileW
            replace.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID]
            replace.restype = wintypes.BOOL
            if not replace(str(path), str(temporary), None, 0, None, None):
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
