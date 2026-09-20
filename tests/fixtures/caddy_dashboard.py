"""Real dashboard routes with only Discord identity lookup replaced offline."""
import os
from dashboard.app import app, api
from fastapi import Request


async def offline_bot():
    return {'id': '1', 'username': 'Offline Tueka', 'avatar': None}


api.bot_user = offline_bot


@app.get('/_acceptance/session')
async def session_cookie(request: Request):
    request.session['acceptance'] = 'offline'
    return {'ok': True}


@app.middleware('http')
async def environment_marker(request, call_next):
    response = await call_next(request)
    response.headers['X-Acceptance-Environment'] = os.environ['TUEKA_ENV']
    return response
