"""Domain service for submissions, votes, and review transitions."""
from __future__ import annotations

from typing import Any

from .models import normalize_settings
from .repository import SuggestionRepository


class SuggestionService:
    def __init__(self, repository: SuggestionRepository) -> None:
        self.repository = repository

    @staticmethod
    def validate_answers(settings: dict[str, Any], answers: dict[str, str]) -> dict[str, str]:
        normalized = normalize_settings(settings)
        clean: dict[str, str] = {}
        for field in normalized["form_fields"]:
            value = str(answers.get(field["key"], "")).strip()
            if field["required"] and not value:
                raise ValueError(f"{field['label']}は必須です。")
            if value and not field["min_length"] <= len(value) <= field["max_length"]:
                raise ValueError(f"{field['label']}は{field['min_length']}～{field['max_length']}文字で入力してください。")
            clean[field["key"]] = value
        return clean

    def submit(self, guild_id: int, channel_id: int, author_id: int, settings: dict[str, Any], answers: dict[str, str]) -> dict[str, Any]:
        return self.repository.create(guild_id, channel_id, author_id, self.validate_answers(settings, answers))

    def vote(self, guild_id: int, suggestion_id: int, user_id: int, value: int, settings: dict[str, Any]) -> dict[str, Any]:
        if not normalize_settings(settings)["allow_voting"]:
            raise PermissionError("voting_disabled")
        return self.repository.vote(guild_id, suggestion_id, user_id, value)

    def review(self, guild_id: int, suggestion_id: int, reviewer_id: int, status: str) -> dict[str, Any]:
        return self.repository.review(guild_id, suggestion_id, reviewer_id, status)
