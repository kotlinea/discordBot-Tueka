"""Allowlisted JSON metadata; raw messages/arguments/exception text are omitted."""
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import re
import sys
import traceback

SERVICES = {'bot', 'dashboard', 'social-worker', 'migrate', 'test', 'unknown'}
EVENTS = {'application_log', 'http_request', 'heartbeat_failed', 'service_started', 'service_stopped'}


def identifier(value):
    return re.sub(r'[^a-zA-Z0-9_.-]', '_', str(value))[:100]


class SafeJsonFormatter(logging.Formatter):
    def __init__(self, service=None):
        super().__init__()
        self.service = service or os.getenv('TUEKA_SERVICE', 'unknown')

    def format(self, record):
        event = getattr(record, 'event_code', 'application_log')
        result = {'time': datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                  'level': record.levelname, 'service': self.service if self.service in SERVICES else 'unknown',
                  'event': event if event in EVENTS else 'application_log',
                  'logger': identifier(record.name), 'function': identifier(record.funcName), 'line': record.lineno}
        for field in ('status', 'duration_ms'):
            value = getattr(record, field, None)
            if isinstance(value, (int, float)) and math.isfinite(value):
                result[field] = value
        if record.exc_info and record.exc_info[0]:
            result['exception_type'] = identifier(record.exc_info[0].__name__)
            result['frames'] = [{'file': identifier(Path(frame.filename).name), 'function': identifier(frame.name), 'line': frame.lineno}
                                for frame in traceback.extract_tb(record.exc_info[2])[-8:]]
        return json.dumps(result, ensure_ascii=True, allow_nan=False)


def configure_logging(service, level='INFO'):
    logging.captureWarnings(True)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(SafeJsonFormatter(service))
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(handlers=[handler], level=numeric_level if isinstance(numeric_level, int) else logging.INFO, force=True)
    for name in ('uvicorn', 'uvicorn.error', 'uvicorn.access', 'discord', 'httpx', 'httpcore', 'psycopg.pool'):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    logging.getLogger('uvicorn.access').disabled = True

    def unhandled(kind, error, trace):
        logging.getLogger('tueka.runtime').critical('Unhandled failure', exc_info=(kind, error, trace))

    sys.excepthook = unhandled
