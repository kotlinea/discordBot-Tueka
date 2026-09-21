"""Moderation API routes."""
from __future__ import annotations
from dashboard.api.errors import api_error, revision_conflict, check_revision
from fastapi import Depends
import secrets
from typing import Any
from fastapi import APIRouter, Header, Request
from moderation import AutoModEngine, MessageContext, default_rule, validate_rule
from dashboard.discord_api import ADMINISTRATOR, PERMISSION_BITS
from dashboard.api.context import ApiContext
from dashboard.api.route import ApiRoute, ERROR_RESPONSES
from dashboard.api import schemas
from dashboard.api.schemas import inputs
from dashboard.api.body import read_body, request_schema
from dashboard.api.dependencies import ApiDependencies
from dashboard.api.serialization import _serialize_rule_resource_ids

def create_router(context: ApiContext) -> APIRouter:
    router = APIRouter(route_class=ApiRoute, responses=ERROR_RESPONSES)
    auth = ApiDependencies(context.dashboard_repository, context.discord)
    discord = context.discord
    moderation_repository = context.moderation_repository
    guild_settings_repository = context.guild_settings_repository
    manage = auth.manage

    @router.get('/guilds/{guild_id}/moderation/infractions/{user_id}', response_model=schemas.InfractionsResponse, response_model_exclude_unset=True)
    async def infractions(request: Request, guild_id: int, user_id: int, _access: str=Depends(auth.read)) -> dict[str, Any]:
        return {'user_id': str(user_id), 'active_points': moderation_repository.active_points(guild_id, user_id), 'cases': moderation_repository.recent_cases(guild_id, user_id, 100)}

    return router
