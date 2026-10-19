"""Private appeal conversation contracts."""
from typing import Literal
from pydantic import Field
from .base import ApiModel

class AppealItem(ApiModel):
    id:int
    guild_id:str
    author_id:str
    kind:Literal['appeal','modmail']
    case_id:int|None
    original_moderator_id:str|None
    case_action:str|None
    application_id:int|None
    ticket_id:int|None
    status:Literal['open','reviewing','accepted','rejected','closed','withdrawn']
    revision:int
    created_at:int
    updated_at:int
    expires_at:int

class AppealMessage(ApiModel):
    id:int
    actor_id:str
    staff:bool
    content:str
    created_at:int

class AppealEvent(ApiModel):
    id:int
    actor_id:str
    event_type:str
    reason:str
    created_at:int

class AppealDelivery(ApiModel):
    id:int
    status:str
    attempts:int
    delivery_started:bool
    discord_message_id:str|None

class AppealConversation(ApiModel):
    messages:list[AppealMessage]
    events:list[AppealEvent]
    delivery:list[AppealDelivery]

class AppealReplyInput(ApiModel):
    content:str=Field(min_length=1,max_length=2000)
    revision:int=Field(ge=1)

class AppealReviewInput(ApiModel):
    status:Literal['reviewing','accepted','rejected','closed']
    reason:str=Field(min_length=1,max_length=1000)
    revision:int=Field(ge=1)

class AppealTicketInput(ApiModel):
    ticket_id:int=Field(ge=1)
    revision:int=Field(ge=1)

class AppealRetryInput(ApiModel):
    revision:int=Field(ge=1)
