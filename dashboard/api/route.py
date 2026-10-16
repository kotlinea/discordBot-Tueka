"""One JSON error contract for registered dashboard API routes."""
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
import httpx
import math
from dashboard.discord_api import retry_after

from .schemas.common import ErrorResponse


def error_detail(status: int, detail) -> dict:
    if isinstance(detail, dict):
        return {'code': detail.get('code', 'request_failed'),
                'message': detail.get('message', str(detail.get('detail', 'Request failed'))),
                'errors': detail.get('errors', detail.get('fields', []))}
    return {'code': {401: 'authentication_required', 403: 'forbidden', 404: 'not_found',
                     409: 'revision_conflict', 422: 'validation_failed'}.get(status, 'request_failed'),
            'message': str(detail), 'errors': []}


ERROR_RESPONSES = {status: {'model': ErrorResponse} for status in (401, 403, 404, 409, 422, 503)}


class ApiRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def normalized(request):
            try:
                return await handler(request)
            except HTTPException as exc:
                return JSONResponse({'detail': error_detail(exc.status_code, exc.detail)},
                                    status_code=exc.status_code, headers=exc.headers)
            except RequestValidationError as exc:
                errors = [{'path': '.'.join(str(part) for part in item['loc']), 'message': item['msg']}
                          for item in exc.errors()]
                return JSONResponse({'detail': {'code': 'validation_failed', 'message': '入力を確認してください。',
                                               'errors': errors}}, status_code=422)
            except httpx.HTTPError as exc:
                # Do not return upstream URLs, headers, bodies or credentials.
                if (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 401
                        and exc.request.headers.get('Authorization', '').startswith('Bearer ')):
                    return JSONResponse({'detail': {'code': 'authentication_required',
                        'message': 'Discordで再ログインしてください。', 'errors': []}}, status_code=401)
                headers = None
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                    delay = retry_after(exc.response)
                    if delay is not None:
                        headers = {'Retry-After': str(math.ceil(delay))}
                return JSONResponse({'detail': {'code': 'upstream_unavailable',
                    'message': '外部サービスとの通信に失敗しました。少し待ってから再試行してください。',
                    'errors': []}}, status_code=503, headers=headers)
        return normalized
