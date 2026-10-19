"""Application intake and review HTTP contracts."""
from typing import Literal
from pydantic import Field
from .base import ApiModel

class ApplicationField(ApiModel):
    key: str = Field(min_length=1,max_length=40)
    label: str = Field(min_length=1,max_length=45)
    style: Literal['short','paragraph'] = 'paragraph'
    required: bool = True
    min_length: int = Field(default=1,ge=0,le=4000)
    max_length: int = Field(default=1000,ge=1,le=4000)

class ApplicationFormInput(ApiModel):
    title: str = Field(min_length=1,max_length=45)
    description: str = Field(default='',max_length=2000)
    fields: list[ApplicationField] = Field(min_length=1,max_length=5)
    enabled: bool = False
    required_role_ids: list[str] = Field(default_factory=list,max_length=25)
    denied_role_ids: list[str] = Field(default_factory=list,max_length=25)
    account_age_days: int = Field(default=0,ge=0,le=3650)
    member_age_days: int = Field(default=0,ge=0,le=3650)
    cooldown_seconds: int = Field(default=3600,ge=0,le=2592000)
    retention_days: int = Field(default=30,ge=1,le=365)
    revision: int | None = Field(default=None,ge=1)

class ApplicationForm(ApplicationFormInput):
    id: int
    guild_id: str
    revision: int
    created_at: int
    updated_at: int

class ApplicationItem(ApiModel):
    id: int
    guild_id: str
    form_id: int
    author_id: str
    snapshot: ApplicationForm
    answers: dict[str,str]
    status: Literal['pending','reviewing','approved','rejected','withdrawn']
    revision: int
    created_at: int
    updated_at: int
    expires_at: int

class ApplicationReviewInput(ApiModel):
    status: Literal['reviewing','approved','rejected']
    reason: str = Field(min_length=1,max_length=1000)
    revision: int = Field(ge=1)

class ApplicationEvent(ApiModel):
    id: int
    actor_id: str
    event_type: str
    reason: str
    created_at: int
