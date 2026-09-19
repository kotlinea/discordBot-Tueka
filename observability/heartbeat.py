"""Each event loop publishes its readiness, database reachability and metrics."""
import asyncio
from contextlib import suppress
import json
import logging
import os
from pathlib import Path
import tempfile
import time
import uuid

from database.connections import pool_statistics
from .metrics import registry
from .repository import heartbeat, SERVICES


def state_path(service):
    if service not in SERVICES:
        raise ValueError('Unknown service')
    return Path(tempfile.gettempdir()) / ('tueka-health-' + service + '.json')


def local_ready(service, *, max_age=30):
    try:
        state = json.loads(state_path(service).read_text())
        if os.name != 'nt':
            os.kill(int(state['pid']), 0)
        return bool(state['ready']) and 0 <= time.monotonic() - state['monotonic'] <= max_age
    except (OSError, ValueError, KeyError, TypeError):
        return False


class ServiceHeartbeat:
    def __init__(self, service, database_url, *, ready=lambda: True, interval=5):
        self.service, self.database_url, self.ready, self.interval = service, database_url, ready, interval
        self.instance = uuid.uuid4().hex
        self.task = None

    def local_state(self, ready):
        path = state_path(self.service)
        temporary = path.with_suffix('.' + self.instance + '.tmp')
        temporary.write_text(json.dumps({'pid': os.getpid(), 'ready': ready, 'monotonic': time.monotonic()}), encoding='utf-8')
        os.replace(temporary, path)

    async def publish(self, *, stopping=False):
        ready = not stopping and bool(self.ready())
        metrics = registry.snapshot()
        pool_names = {'pool_size': ('db_pool_connections', 1), 'pool_available': ('db_pool_available_connections', 1),
                      'requests_waiting': ('db_pool_waiting_requests', 1), 'requests_queued': ('db_pool_queued_requests_total', 1),
                      'requests_wait_ms': ('db_pool_wait_seconds_total', .001), 'requests_errors': ('db_pool_request_errors_total', 1),
                      'connections_errors': ('db_pool_connection_errors_total', 1)}
        metrics.extend({'name': pool_names[name][0], 'labels': {}, 'value': value * pool_names[name][1]} for name, value in pool_statistics().items())
        try:
            await asyncio.to_thread(heartbeat, self.database_url, self.service, self.instance, ready, metrics)
        except Exception:
            ready = False
            logging.getLogger(__name__).warning('Heartbeat failed', extra={'event_code': 'heartbeat_failed'}, exc_info=True)
        self.local_state(ready)

    async def loop(self):
        while True:
            await asyncio.sleep(self.interval)
            await self.publish()

    async def start(self):
        await self.publish()
        self.task = asyncio.create_task(self.loop())
        return self

    async def stop(self):
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
        self.local_state(False)
        await self.publish(stopping=True)

    async def __aenter__(self):
        return await self.start()

    async def __aexit__(self, *_):
        await self.stop()
