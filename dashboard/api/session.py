"""Session API routes."""
from __future__ import annotations
from .errors import api_error, revision_conflict
from fastapi import Depends
from typing import Any
from fastapi import APIRouter, Request
from dashboard.discord_api import ADMINISTRATOR
from .context import ApiContext
from .route import ApiRoute, ERROR_RESPONSES
from . import schemas
from .schemas import inputs
from .body import read_body, request_schema
from .dependencies import ApiDependencies
from ticketing.access import team_member

def create_router(context: ApiContext) -> APIRouter:
    router = APIRouter(route_class=ApiRoute, responses=ERROR_RESPONSES)
    auth = ApiDependencies(context.dashboard_repository, context.discord)
    discord = context.discord
    dashboard_repository = context.dashboard_repository
    ticket_repository = context.ticket_repository

    @router.get('/session', response_model=schemas.Session, response_model_exclude_unset=True)
    async def session(request: Request, access: str=Depends(auth.token)) -> dict[str, Any]:
        user = await discord.current_user(access)
        avatar_hash = user.get('avatar')
        avatar_url = f"https://cdn.discordapp.com/avatars/{user['id']}/{avatar_hash}.webp?size=128" if avatar_hash else f"https://cdn.discordapp.com/embed/avatars/{(int(user['id']) >> 22) % 6}.png"
        return {'user': {'id': str(user['id']), 'name': user.get('global_name') or user['username'], 'avatar_url': avatar_url}, 'csrf_token': request.session.get('csrf_token', ''), 'preferences': dashboard_repository.dashboard_preferences(int(user['id']))}

    @router.put('/preferences', dependencies=[Depends(auth.csrf)], response_model=schemas.Preferences, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.PreferencesInput))
    async def save_preferences(request: Request, access: str=Depends(auth.token)) -> dict[str, Any]:
        user, body = (await discord.current_user(access), await read_body(request, inputs.PreferencesInput))
        try:
            return dashboard_repository.set_dashboard_preferences(int(user['id']), locale=str(body.get('locale', 'ja')), appearance=str(body.get('appearance', 'precision')), color_scheme=str(body.get('color_scheme', 'system')), navigation_collapsed=bool(body.get('navigation_collapsed', False)), expected_revision=int(body['revision']) if body.get('revision') is not None else None)
        except RuntimeError as exc:
            raise revision_conflict('別の画面で表示設定が更新されました。再読み込みしてください。') from exc
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'preferences_invalid', '表示設定を確認してください。') from exc

    @router.get('/guilds', response_model=schemas.Items[schemas.Guild], response_model_exclude_unset=True)
    async def guilds(request: Request, access: str=Depends(auth.token)) -> dict[str, Any]:
        values = await discord.user_guilds(access)
        bot_guilds = await discord.bot_guild_ids()
        user = await discord.current_user(access)
        user_id = int(user['id'])
        visible = []
        for item in values:
            guild_id = int(item['id'])
            if guild_id not in bot_guilds:
                continue
            administrator = bool(int(item.get('permissions', '0')) & ADMINISTRATOR)
            ticket_staff = False
            if not administrator and ticket_repository:
                teams = ticket_repository.teams(guild_id)
                if teams:
                    member = await discord.guild_member(guild_id, user_id)
                    ticket_staff = any(team_member(team, user_id, member) for team in teams)
            if administrator or ticket_staff:
                visible.append({'id': str(item['id']), 'name': item['name'], 'icon': item.get('icon'), 'access': 'admin' if administrator else 'ticket_staff'})
        return {'items': visible}
    return router
