"""Suggestion workflow primitives shared by Discord and the dashboard."""

from .models import DEFAULT_SETTINGS, SuggestionValidationError, normalize_settings
from .repository import SuggestionRepository
from .service import SuggestionService

__all__ = [
    "DEFAULT_SETTINGS",
    "SuggestionRepository",
    "SuggestionService",
    "SuggestionValidationError",
    "normalize_settings",
]
