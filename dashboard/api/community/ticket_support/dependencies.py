"""Ticket staff and assigned-team access checks."""
from __future__ import annotations
from dashboard.api.errors import api_error
from typing import Any
from fastapi import Request
from dashboard.api.context import ApiContext
from dashboard.api.dependencies import ApiDependencies

def team_member(team: dict[str, Any], user_id: int, member: dict[str, Any] | None) -> bool:
    """An explicit team assignment never grants access after guild membership ends."""
    if member is None:
        return False
    roles = {int(item) for item in member.get('roles', [])}
    return bool(user_id in team.get('user_ids', []) or user_id in team.get('admin_user_ids', [])
                or roles.intersection(team.get('role_ids', [])))


class TicketDependencies:

    def __init__(self, context: ApiContext, auth: ApiDependencies):
        self.auth = auth
        self.discord = context.discord
        self.repository = context.ticket_repository
        self.service = context.ticket_service

    async def staff(self, request: Request, guild_id: int) -> tuple[int, bool]:
        self.tickets_available(guild_id)
        return await self.ticket_actor(request, guild_id)

    async def manager(self, request: Request, guild_id: int) -> tuple[int, bool]:
        self.tickets_available(guild_id)
        return await self.ticket_actor(request, guild_id, require_manage=True)

    async def write_staff(self, request: Request, guild_id: int) -> tuple[int, bool]:
        self.tickets_available(guild_id)
        return await self.ticket_actor(request, guild_id, live=True)

    async def write_manager(self, request: Request, guild_id: int) -> tuple[int, bool]:
        self.tickets_available(guild_id)
        return await self.ticket_actor(request, guild_id, require_manage=True, live=True)

    def tickets_available(self, guild_id: int) -> None:
        if not self.repository or not self.service:
            raise api_error(503, 'tickets_unavailable', 'Ticketを初期化できません。')

    async def ticket_actor(self, request: Request, guild_id: int, *, require_manage: bool=False, live: bool=False) -> tuple[int, bool]:
        access = self.auth.token(request)
        user = await self.discord.current_user(access)
        user_id = int(user['id'])
        administrator = await self.discord.can_manage(access, guild_id, use_cache=not live)
        if administrator:
            return (user_id, True)
        if require_manage:
            raise api_error(403, 'guild_forbidden', '管理者権限が必要です。')
        member = await self.discord.guild_member(guild_id, user_id, use_cache=not live)
        if member is None:
            raise api_error(403, 'ticket_staff_forbidden', 'Ticket Staff権限がありません。')
        teams = self.repository.teams(guild_id) if self.repository else []
        if any(team_member(team, user_id, member) for team in teams):
            return (user_id, False)
        raise api_error(403, 'ticket_staff_forbidden', 'Ticket Staff権限がありません。')

    async def ticket_subject_access(self, request: Request, guild_id: int, ticket: dict[str, Any], actor_id: int, administrator: bool) -> None:
        if administrator:
            return
        panel = self.repository.panel(guild_id, int(ticket['panel_id'])) if self.repository else None
        team = self.repository.team(guild_id, int(panel['team_id'])) if panel and panel.get('team_id') else None
        member = await self.discord.guild_member(guild_id, actor_id, use_cache=request.method in {'GET', 'HEAD'})
        if not team or not team_member(team, actor_id, member):
            raise api_error(403, 'ticket_team_forbidden', 'このTicketを担当するTeamの権限が必要です。')
