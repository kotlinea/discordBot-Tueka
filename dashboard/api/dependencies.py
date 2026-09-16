"""Shared OAuth session, CSRF, and guild access dependencies."""
from __future__ import annotations
from .errors import api_error
import secrets
from typing import Any
from fastapi import Request
from dashboard.repository import DashboardRepository

class ApiDependencies:

    def __init__(self, repository: DashboardRepository, discord: Any):
        self.discord = discord
        self.repository = repository

    def token_or_none(self, request: Request) -> str | None:
        session_id = request.session.get('session_id')
        return self.repository.dashboard_session_token(session_id) if session_id else None

    def token(self, request: Request) -> str:
        value = self.token_or_none(request)
        if not value:
            raise api_error(401, 'authentication_required', 'ログインが必要です。')
        return value

    async def manage(self, request: Request, guild_id: int, *, live: bool=False) -> str:
        value = self.token(request)
        if not await self.discord.can_manage(value, guild_id, use_cache=not live):
            raise api_error(403, 'guild_forbidden', 'このサーバーを管理する権限がありません。')
        return value

    async def read(self, request: Request, guild_id: int) -> str:
        return await self.manage(request, guild_id)

    async def write(self, request: Request, guild_id: int) -> str:
        return await self.manage(request, guild_id, live=True)

    def csrf(self, request: Request) -> None:
        supplied = request.headers.get('x-csrf-token', '')
        if not self.valid_csrf(request, supplied):
            raise api_error(403, 'csrf_invalid', '画面を再読み込みして、もう一度保存してください。')

    @staticmethod
    def valid_csrf(request: Request, supplied: str | None) -> bool:
        expected = request.session.get('csrf_token')
        return bool(supplied and expected and secrets.compare_digest(str(supplied), str(expected)))

    async def resources(self, request: Request, guild_id: int, *, live: bool=False) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
        await self.manage(request, guild_id, live=live)
        return await self.discord.guild_resources(guild_id, use_cache=not live)
