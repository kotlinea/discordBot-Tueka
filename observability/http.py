"""Minimal health responses and authenticated operational metrics."""
import hmac
import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from .repository import database_ready, snapshot
from .export import render
from .metrics import registry


def router(database_url, assets, token, *, heartbeat_age=30, queue_age=300):
    result = APIRouter(include_in_schema=False)

    @result.get('/health/live')
    async def live():
        return {'status': 'ok'}

    @result.get('/health/ready')
    def ready():
        try:
            ok = all((path / 'index.html').is_file() for path in assets) and database_ready(database_url)
        except Exception:
            ok = False
        return JSONResponse({'status': 'ok' if ok else 'unavailable'}, status_code=200 if ok else 503)

    @result.get('/internal/metrics')
    def metrics(request: Request):
        supplied = request.headers.get('authorization', '')
        if not token or len(token) < 32 or not hmac.compare_digest(supplied.encode(), ('Bearer ' + token).encode()):
            return PlainTextResponse('Not found', status_code=404)
        try:
            return PlainTextResponse(render(snapshot(database_url, heartbeat_age=heartbeat_age, queue_age=queue_age)), media_type='text/plain; version=0.0.4')
        except Exception:
            return PlainTextResponse('tueka_database_up 0\n', status_code=503)

    return result


async def observe_request(request, call_next):
    started, status = time.monotonic(), 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = getattr(request.scope.get('route'), 'path', 'unmatched')
        method = request.method if request.method in {'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'} else 'OTHER'
        registry.add('http_requests_total', route=route, method=method, status=str(status // 100) + 'xx')
        registry.observe('http_request_seconds', time.monotonic() - started, route=route, method=method)
        logging.getLogger('tueka.http').info('Request', extra={'event_code': 'http_request', 'status': status, 'duration_ms': round((time.monotonic()-started)*1000, 2)})
