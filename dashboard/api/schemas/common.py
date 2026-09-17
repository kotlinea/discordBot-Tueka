"""common HTTP schemas."""
from __future__ import annotations
from typing import Any, Literal
from .base import ApiModel


Locale = Literal["ja"] | Literal["en"]


Appearance = Literal["precision"] | Literal["community"] | Literal["atmosphere"]


ColorScheme = Literal["system"] | Literal["light"] | Literal["dark"]


class Preferences(ApiModel):
    locale: Locale
    appearance: Appearance
    color_scheme: ColorScheme
    navigation_collapsed: bool
    revision: int


class SessionUser(ApiModel):
    id: str
    name: str
    avatar_url: str


class Session(ApiModel):
    user: SessionUser
    csrf_token: str
    preferences: Preferences


class Guild(ApiModel):
    id: str
    name: str
    icon: str | None
    access: Literal["admin"] | Literal["ticket_staff"] = None


class Resource(ApiModel):
    id: str
    name: str
    type: int = None
    position: int = None
    animated: bool = None


class Feature(ApiModel):
    id: str
    category: str
    parent: str | None
    docs_path: str
    title: str
    description: str
    fields: list[str]
    required_fields: list[str]
    required_bot_permissions: list[str]
    enabled: bool
    settings: dict[str, Any]
    revision: int
    missing_permissions: list[str]


from typing import Generic, TypeVar
from pydantic import Field, model_validator

T = TypeVar('T')


class Items(ApiModel, Generic[T]):
    items: list[T]
    next: int | None = None

    @model_validator(mode='before')
    @classmethod
    def cursor(cls, value):
        return {'next': None, **value} if isinstance(value, dict) else value


class Resources(ApiModel):
    channels: list[Resource]
    roles: list[Resource]
    emojis: list[Resource] = []
    bot_permissions: str


class StatusResponse(ApiModel):
    status: str


class QueuedResponse(StatusResponse):
    id: int


class ModuleValue(ApiModel):
    enabled: bool
    settings: dict[str, Any]
    revision: int


class Diagnostic(ApiModel):
    level: str
    message: str


class PreviewResponse(ApiModel):
    diagnostics: list[Diagnostic]


class ErrorField(ApiModel):
    path: str
    message: str


class ErrorDetail(ApiModel):
    code: str
    message: str
    errors: list[ErrorField] = []


class ErrorResponse(ApiModel):
    detail: ErrorDetail
