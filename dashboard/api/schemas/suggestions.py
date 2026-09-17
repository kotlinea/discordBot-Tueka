"""suggestions HTTP schemas."""
from __future__ import annotations
from typing import Any, Literal
from .base import ApiModel
from pydantic import Field


class SuggestionFormField(ApiModel):
    key: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=45)
    placeholder: str = Field(max_length=100)
    style: Literal["short"] | Literal["paragraph"]
    required: bool
    min_length: int = Field(ge=0, le=4000)
    max_length: int = Field(ge=1, le=4000)


class SuggestionSettings(ApiModel):
    channel_id: str | None
    log_channel_id: str | None
    review_role_ids: list[str] = Field(max_length=25)
    allow_voting: bool
    show_author: bool
    form_title: str = Field(min_length=1, max_length=45)
    form_fields: list[SuggestionFormField] = Field(min_length=1, max_length=5)


class SuggestionItem(ApiModel):
    id: int
    author_id: str
    message_id: str | None
    status: Literal["pending"] | Literal["reviewing"] | Literal["approved"] | Literal["rejected"] | Literal["delivery_failed"]
    answers: dict[str, str]
    upvotes: int
    downvotes: int
    reviewer_id: str | None
    created_at: int
    revision: int


from .common import Feature


class SuggestionFeature(Feature):
    settings: SuggestionSettings
