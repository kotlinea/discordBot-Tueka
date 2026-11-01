"""Advanced poll HTTP input and filtered output schemas."""
from typing import Literal
from pydantic import Field, ConfigDict
from .base import ApiModel

PollMode = Literal['public','anonymous','secret_winner','reveal_at_end','blind','custom']


class PollConfig(ApiModel):
    model_config = ConfigDict(extra='forbid')
    question: str = Field(min_length=1,max_length=1024)
    description: str = Field(default='',max_length=2000)
    options: list[str] = Field(min_length=2,max_length=25)
    emojis: list[str] | None = None
    max_choices: int = Field(default=1,ge=1,le=20)
    mode: PollMode = 'anonymous'
    visibility: dict[str,dict[str,str]] | None = None
    ui: Literal['buttons','select'] = 'buttons'
    button_style: Literal['primary','secondary','success','danger'] = 'secondary'
    image_url: str | None = Field(default=None,max_length=2048)
    color: int = Field(default=0x5865F2,ge=0,le=0xffffff)
    max_participants: int | None = Field(default=None,ge=1,le=1000000)
    allowed_roles: list[str] = Field(default_factory=list,max_length=100)
    denied_roles: list[str] = Field(default_factory=list,max_length=100)
    denied_users: list[str] = Field(default_factory=list,max_length=100)
    announce_winner: bool = False
    pin_on_close: bool = False
    create_thread: bool = False
    remove_departed_votes: bool = False


class PollRevisionInput(ApiModel):
    revision: int = Field(ge=1)


class PollRemoveVoteInput(PollRevisionInput):
    user_id: str


class PollCreateInput(ApiModel):
    config: PollConfig
    channel_id: str
    request_key: str = Field(min_length=1,max_length=100)
    scheduled_at: int | None = None
    duration_seconds: int | None = Field(default=None,ge=1,le=2592000)
    closes_at: int | None = None


class PollEditInput(ApiModel):
    config: PollConfig
    revision: int = Field(ge=1)
    closes_at: int | None = None
    scheduled_at: int | None = None
    duration_seconds: int | None = None


class PollActionInput(ApiModel):
    revision: int = Field(ge=1)
    action: Literal['launch','close','reopen','cancel','delete','copy','move']
    channel_id: str | None = None
    closes_at: int | None = None
    request_key: str | None = Field(default=None,max_length=100)


class PollBallot(ApiModel):
    user_id: str
    choices: list[int]
    weight: int


class PollItem(ApiModel):
    id: int
    guild_id: str
    channel_id: str
    message_id: str | None = None
    status: str
    revision: int
    closes_at: int | None = None
    created_at: int
    scheduled_at: int | None = None
    duration_seconds: int | None = None
    published_at: int | None = None
    config: PollConfig
    counts: list[int] | None = None
    weighted_counts: list[int] | None = None
    ranking: list[int] | None = None
    total: int | None = None
    selections: int | None = None
    participants: list[str] | None = None
    ballots: list[PollBallot] | None = None


class PollCapabilities(ApiModel):
    permissions: list[str]
    enabled: bool


class PollEvent(ApiModel):
    id: int
    actor_id: str | None
    event_type: str
    created_at: int


class PollDeliveryItem(ApiModel):
    id: int
    action: str
    status: str
    attempts: int
    last_error: str | None
    discord_receipt_id: str | None


class PollHistory(ApiModel):
    events: list[PollEvent]
    delivery: list[PollDeliveryItem]


class PollSettings(ApiModel):
    retention_days: int = Field(default=90,ge=1,le=365)
    role_weights: dict[str,int] = Field(default_factory=dict)
    role_permissions: dict[str,list[str]] = Field(default_factory=dict)


class PollSettingsItem(ApiModel):
    revision: int
    enabled: bool = False
    settings: PollSettings


class PollSettingsInput(PollSettingsItem):
    pass
