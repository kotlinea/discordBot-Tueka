"""Guilds API routes."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Request
from feature_registry import FEATURES
from .context import ApiContext
from .dependencies import ApiDependencies
from .features import FeaturePresenter

def create_router(context: ApiContext) -> APIRouter:
    router = APIRouter()
    auth = ApiDependencies(context.dashboard_repository, context.discord)
    discord = context.discord
    moderation_repository = context.moderation_repository
    resources = auth.resources
    feature_payload = FeaturePresenter(context).feature_payload

    @router.get('/guilds/{guild_id}/overview')
    async def overview(request: Request, guild_id: int) -> dict[str, Any]:
        channels, roles, permissions = await resources(request, guild_id)
        features = [feature_payload(guild_id, feature, permissions) for feature in FEATURES]
        return {'guild_id': str(guild_id), 'features': features, 'resources': {'channels': channels, 'roles': roles, 'bot_permissions': str(permissions)}, 'moderation': {'summary': moderation_repository.moderation_summary(guild_id), 'events': moderation_repository.recent_moderation_events(guild_id, limit=10), 'lockdown': moderation_repository.active_lockdown(guild_id)}}

    @router.get('/guilds/{guild_id}/features')
    async def features(request: Request, guild_id: int) -> dict[str, Any]:
        _, _, permissions = await resources(request, guild_id)
        return {'items': [feature_payload(guild_id, feature, permissions) for feature in FEATURES]}

    @router.get('/guilds/{guild_id}/resources')
    async def guild_resources(request: Request, guild_id: int) -> dict[str, Any]:
        channels, roles, permissions = await resources(request, guild_id)
        emojis = await discord.guild_emojis(guild_id)
        return {'channels': channels, 'roles': roles, 'emojis': emojis, 'bot_permissions': str(permissions)}
    return router
