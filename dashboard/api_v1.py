"""Compose the public /api/v1 contract from domain routers."""
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from dashboard.api.context import create_context
from dashboard.api import session, guilds, suggestions, social, ticket_configuration, tickets, reaction_roles, modules, moderation


def create_api_router(database_path: str | Path, discord: Any, settings: Any | None = None) -> APIRouter:
    context = create_context(database_path, discord, settings)
    router = APIRouter(prefix="/api/v1")
    router.include_router(session.create_router(context))
    router.include_router(guilds.create_router(context))
    router.include_router(suggestions.create_router(context))
    router.include_router(social.create_router(context))
    router.include_router(ticket_configuration.create_router(context))
    router.include_router(tickets.create_router(context))
    router.include_router(reaction_roles.create_router(context))
    router.include_router(modules.create_router(context))
    router.include_router(moderation.create_router(context))
    return router
