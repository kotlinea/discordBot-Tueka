"""Reaction Roles domain package."""

from .models import (
    BEHAVIOR_TYPES,
    LINKABLE_TYPES,
    ReactionRoleValidationError,
    default_message,
    normalize_emoji,
    validate_message,
)
from .repository import ReactionRoleRepository
from .service import ReactionDecision, ReactionRoleService

__all__ = [
    "BEHAVIOR_TYPES",
    "LINKABLE_TYPES",
    "ReactionDecision",
    "ReactionRoleRepository",
    "ReactionRoleService",
    "ReactionRoleValidationError",
    "default_message",
    "normalize_emoji",
    "validate_message",
]
