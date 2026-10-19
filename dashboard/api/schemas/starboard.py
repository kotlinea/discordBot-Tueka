"""Explicit highlight configuration and delivery history contracts."""
from pydantic import Field
from .base import ApiModel


class StarboardConfig(ApiModel):
    name:str=Field(min_length=1,max_length=80)
    enabled:bool=Field(default=False,strict=True)
    target_channel_id:str
    source_channel_ids:list[str]=Field(min_length=1,max_length=25)
    excluded_channel_ids:list[str]=Field(default_factory=list,max_length=25)
    emoji:str=Field(default='⭐',min_length=1,max_length=80)
    threshold:int=Field(default=3,ge=1,le=100,strict=True)
    retention_days:int=Field(default=30,ge=1,le=365,strict=True)


class StarboardCreateInput(ApiModel):
    config:StarboardConfig
    request_key:str=Field(min_length=1,max_length=100)


class StarboardEditInput(ApiModel):
    config:StarboardConfig
    revision:int=Field(ge=1,strict=True)


class StarboardRevisionInput(ApiModel):
    revision:int=Field(ge=1,strict=True)


class StarboardItem(ApiModel):
    id:int
    guild_id:str
    actor_id:str
    config:StarboardConfig
    revision:int
    created_at:int
    updated_at:int


class HighlightSource(ApiModel):
    guild_id:str
    channel_id:str
    message_id:str
    parent_channel_id:str|None=None
    author_id:str
    author_name:str=''
    content:str=''
    image_url:str=''
    author_bot:bool=False
    nsfw:bool=False
    deleted:bool=False


class HighlightEntry(ApiModel):
    id:int
    board_id:int
    guild_id:str
    source_channel_id:str
    source_message_id:str
    snapshot:HighlightSource
    score:int
    desired:bool
    revision:int
    created_at:int
    updated_at:int
    expires_at:int


class HighlightEvent(ApiModel):
    id:int
    board_id:int
    entry_id:int|None
    actor_id:str
    event_type:str
    detail:dict
    created_at:int


class HighlightJob(ApiModel):
    id:int
    entry_id:int
    status:str
    attempts:int
    last_error:str|None


class HighlightPublication(ApiModel):
    id:int
    entry_id:int
    target_channel_id:str
    message_id:str|None
    delivery_started:bool
    removed:bool


class HighlightSourceJob(ApiModel):
    id:int
    channel_id:str
    message_id:str
    status:str
    attempts:int
    last_error:str|None
    retry_actor_id:str|None
    retry_at:int|None


class HighlightHistory(ApiModel):
    events:list[HighlightEvent]
    delivery:list[HighlightJob]
    publications:list[HighlightPublication]
    source_fetches:list[HighlightSourceJob]
