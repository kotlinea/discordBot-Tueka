"""Compose the public /api/v1 contract from domain routers."""
from typing import Any

from fastapi import APIRouter
from dashboard.api.context import create_context
from dashboard.api.composition import build_routers
from dashboard.icon_registry import validate_feature_icons
from features.loading import resolve_bindings
from features.registry import REGISTRY, FEATURES


def create_api_router(database_url: str, discord: Any, settings: Any | None = None) -> APIRouter:
    validate_feature_icons(FEATURES)
    factories = resolve_bindings(REGISTRY.for_process('api'))
    context = create_context(database_url, discord, settings)
    router = APIRouter(prefix="/api/v1")
    for child in build_routers(factories, context):
        router.include_router(child)
    return router
