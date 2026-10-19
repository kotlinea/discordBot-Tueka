"""Operation inputs; omitted values are normalized by each domain."""
from typing import Any, Literal
from pydantic import Field
from .base import ApiModel, input_model
from .common import Preferences, ModuleValue
from .moderation import Rule
from .social import SocialTemplate
from .suggestions import SuggestionSettings
from .tickets import TicketSettings, TicketForm, TicketTeam, TicketPanel, TicketPanelBundle, TicketPanelMessage, TicketDeployment
from .reaction_roles import ReactionRoleMessage, ReactionRoleSettings

PreferencesInput = input_model(Preferences)
ModuleInput = input_model(ModuleValue)
RuleInput = input_model(Rule)
TicketSettingsInput = input_model(TicketSettings)
TicketFormInput = input_model(TicketForm)
TicketTeamInput = input_model(TicketTeam)
TicketPanelInput = input_model(TicketPanel)
TicketPanelBundleInput = input_model(TicketPanelBundle)
TicketPanelMessageInput = input_model(TicketPanelMessage)
ReactionRoleSettingsInput = input_model(ReactionRoleSettings)


class SuggestionInput(ApiModel):
    enabled: bool = False
    revision: int | None = None
    settings: input_model(SuggestionSettings) = Field(default_factory=dict)


class SocialInput(ApiModel):
    account: str = ''
    channel_id: str | int | None = None
    role_id: str | int | None = None
    events: list[str] = []
    event_channels: dict[str, str | int] = {}
    templates: dict[str, input_model(SocialTemplate)] = {}
    enabled: bool = True
    revision: int | None = None


class SocialPreviewInput(ApiModel):
    event: str = ''
    template: input_model(SocialTemplate) = Field(default_factory=dict)


class ReactionRoleInput(input_model(ReactionRoleMessage)):
    message: input_model(ReactionRoleMessage) | None = None


class ReorderItem(ApiModel):
    id: int
    revision: int
    stop_on_match: bool = False


class ReorderInput(ApiModel):
    items: list[ReorderItem] = []


class RuleStateItem(ApiModel):
    id: int = Field(gt=0, strict=True)
    revision: int = Field(gt=0, strict=True)


class RuleStateInput(ApiModel):
    items: list[RuleStateItem] = Field(min_length=1, max_length=200)
    enabled: bool = Field(strict=True)


class RuleTestInput(ApiModel):
    content: str = Field(default='', max_length=4000)
    channel_id: str | int | None = None
    mentions: int = Field(default=0, ge=0, le=100)
    attachments: int = Field(default=0, ge=0, le=20)
    stickers: int = Field(default=0, ge=0, le=100)


class RulePreviewInput(ApiModel):
    rule: RuleInput = Field(default_factory=dict)
    input: RuleTestInput = Field(default_factory=dict)


class ModerationActionInput(ApiModel):
    action: str = ''
    target_user_id: str | int | None = None
    channel_id: str | int | None = None
    reason: str = Field(default='', max_length=500)
    confirmed: bool = False
    confirmation: str = ''
    duration_minutes: int = Field(default=10, ge=1, le=525600)
    count: int = Field(default=10, ge=1, le=100)


class MoveInput(ApiModel):
    channel_id: str | int = 0
    message_id: str | int = 0


class LinkGroupInput(ApiModel):
    name: str = ''
    message_ids: list[int] = []


class DetachInput(ApiModel):
    panel_message_id: int | None = None


class TicketImportInput(ApiModel):
    schema_version: str = Field(default='', alias='schema')
    panel: TicketPanelInput = Field(default_factory=dict)
    mapping: TicketPanelInput = Field(default_factory=dict)


class TicketTagInput(ApiModel):
    name: str = ''
    content: str = Field(default='', max_length=2000)


class TicketReplyInput(ApiModel):
    content: str = Field(default='', max_length=2000)
    anonymous: bool = False
    note: bool = False


class TicketActionInput(ApiModel):
    action: str = ''
    reason: str = Field(default='', max_length=1000)
    revision: int | None = None
    excluded: bool = True


class SuggestionReviewInput(ApiModel):
    status: Literal['reviewing', 'approved', 'rejected', 'implemented']
    reason: str = Field(min_length=1, max_length=1000)
    revision: int = Field(ge=1)


class FeedbackInput(ApiModel):
    rating: int = Field(default=0, ge=1, le=5)
    comment: str = Field(default='', max_length=1000)
    answers: dict[str, str] = {}
