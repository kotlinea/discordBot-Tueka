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

    @router.get('/guilds/{guild_id}/moderation/events', response_model=schemas.Items[schemas.ModerationEvent], response_model_exclude_unset=True)
    async def events(request: Request, guild_id: int, family: str | None=None, user_id: int | None=None, limit: int=50, _access: str=Depends(auth.read)) -> dict[str, Any]:
        return {'items': moderation_repository.recent_moderation_events(guild_id, family=family, user_id=user_id, limit=limit)}

    return router
