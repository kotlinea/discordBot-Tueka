"""tickets HTTP schemas."""
from __future__ import annotations
from typing import Any, Literal
from .base import ApiModel
from pydantic import Field


class TicketSettingsDefaultAutoClose(ApiModel):
    on_member_leave: bool
    no_user_reply_minutes: int
    inactivity_minutes: int


class TicketSettings(ApiModel):
    enabled: bool
    open_limit: int
    language: Literal["ja"] | Literal["en"]
    log_channel_id: str | None
    transcript_channel_id: str | None
    transcript_retention_days: int
    close_dm: bool
    default_auto_close: TicketSettingsDefaultAutoClose
    revision: int


class TicketItem(ApiModel):
    id: int
    ticket_number: int
    guild_id: str
    panel_id: int
    opener_id: str
    mode: Literal["channel"] | Literal["private_thread"]
    status: str
    discord_container_id: str | None
    claimed_by: str | None
    form_answers: dict[str, str] = None
    auto_close_excluded: bool
    created_at: int
    opened_at: int | None = None
    closed_at: int | None = None
    revision: int


class TicketEmbedAuthor(ApiModel):
    enabled: bool
    name: str = Field(max_length=256)
    icon_url: str
    url: str


class TicketEmbedFooter(ApiModel):
    enabled: bool
    text: str = Field(max_length=2048)
    icon_url: str
    timestamp: bool


class TicketEmbedFieldsItem(ApiModel):
    name: str = Field(max_length=256)
    value: str = Field(max_length=1024)
    inline: bool


class TicketEmbed(ApiModel):
    color: str
    title: str = Field(max_length=256)
    title_url: str
    description: str = Field(max_length=4096)
    author: TicketEmbedAuthor
    image_url: str
    thumbnail_url: str
    footer: TicketEmbedFooter
    fields: list[TicketEmbedFieldsItem] = Field(max_length=25)


class TicketAccessRule(ApiModel):
    role_id: str
    label: str
    allow: bool


class TicketPermissions(ApiModel):
    add_reactions: bool
    send_tts_messages: bool
    embed_links: bool
    attach_files: bool
    use_external_emojis: bool
    use_external_stickers: bool
    send_voice_messages: bool


class TicketPanelButton(ApiModel):
    style: Literal["primary"] | Literal["secondary"] | Literal["success"] | Literal["danger"]
    label: str = Field(max_length=80)
    emoji: str


class TicketPanelSupportHoursWeekdaysValue(ApiModel):
    start: str = Field(pattern=r'^([01][0-9]|2[0-3]):[0-5][0-9]$')
    end: str = Field(pattern=r'^([01][0-9]|2[0-3]):[0-5][0-9]$')


class TicketPanelSupportHours(ApiModel):
    timezone: str
    weekdays: dict[str, TicketPanelSupportHoursWeekdaysValue]


class TicketPanel(ApiModel):
    id: int = None
    name: str
    description: str
    mode: Literal["channel"] | Literal["private_thread"]
    form_id: int | None
    team_id: int | None
    category_id: str | None
    thread_parent_channel_id: str | None
    staff_notification_channel_id: str | None
    transcript_channel_id: str | None
    awaiting_category_id: str | None
    exit_form_id: int | None
    mention_role_ids: list[str]
    remove_mentions: bool
    open_cooldown_seconds: int
    per_user_open_limit: int
    ticket_name_template: str
    claim_mode: str
    allow_user_close: bool
    feedback_enabled: bool
    show_claim_button: bool
    show_close_button: bool
    show_close_reason_button: bool
    button: TicketPanelButton
    welcome_embed: TicketEmbed
    creator_permissions: TicketPermissions
    access_rules: list[TicketAccessRule]
    support_hours: TicketPanelSupportHours
    enabled: bool
    revision: int = None


class TicketFormFieldsItem(ApiModel):
    key: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=45)
    placeholder: str = Field(max_length=100)
    style: Literal["short"] | Literal["paragraph"]
    required: bool
    min_length: int = Field(ge=0, le=4000)
    max_length: int = Field(ge=1, le=4000)


class TicketForm(ApiModel):
    id: int
    name: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=45)
    fields: list[TicketFormFieldsItem] = Field(max_length=5)
    revision: int


class TicketTeam(ApiModel):
    id: int
    name: str
    role_ids: list[str]
    user_ids: list[str]
    admin_user_ids: list[str]
    notification_channel_id: str | None
    enabled: bool
    revision: int


class TicketPanelMessage(ApiModel):
    id: int
    name: str
    channel_id: str
    message_id: str | None
    title: str
    description: str
    color: str
    content: str = None
    image_url: str = None
    thumbnail_url: str = None
    panel_ids: list[int]
    status: str
    last_error: str | None = None
    revision: int


class TicketDeployment(ApiModel):
    panel_message_id: int | None
    revision: int | None
    name: str
    channel_id: str | None
    content: str = Field(max_length=2000)
    title: str = Field(max_length=256)
    description: str = Field(max_length=4096)
    color: str
    image_url: str
    thumbnail_url: str
    position: int | None


class TicketPanelBundleSupportHoursWeekdaysValue(ApiModel):
    start: str
    end: str


class TicketPanelBundleSupportHours(ApiModel):
    timezone: str
    weekdays: dict[str, TicketPanelBundleSupportHoursWeekdaysValue]


class TicketPanelBundle(ApiModel):
    panel: TicketPanel
    deployment: TicketDeployment | None
    deployments: list[TicketPanelMessage] = None
    welcome_embed: TicketEmbed
    permissions: TicketPermissions
    access_rules: list[TicketAccessRule]
    support_hours: TicketPanelBundleSupportHours


class TicketTag(ApiModel):
    id: int
    name: str
    content: str


class TicketSummary(ApiModel):
    open: int
    unclaimed: int
    closed_30d: int
    average_rating: float | None


class TicketMessage(ApiModel):
    id: int
    author_name: str
    kind: str
    content: str
    author_id: str | None = None
    discord_message_id: str | None = None
    created_at: int


class TranscriptReference(ApiModel):
    id: int | None = None


class TranscriptTicket(ApiModel):
    id: int
    ticket_number: int
    guild_id: str
    panel_id: int
    opener_id: str
    mode: str
    created_at: int
    opened_at: int | None


class TranscriptMessage(ApiModel):
    id: int
    discord_message_id: str | None = None
    author_id: str | None = None
    author: str | None
    kind: str
    content: str
    created_at: int
    deleted_at: int | None = None
    edited_at: int | None = None


class TranscriptAttachment(ApiModel):
    id: int
    filename: str
    content_type: str | None
    size: int


class TicketPanelPreview(ApiModel):
    panel_message: TicketDeployment
    button: TicketPanelButton
    welcome_message: TicketEmbed


class TicketOverview(ApiModel):
    settings: TicketSettings
    summary: TicketSummary
    recent: list[TicketItem]
    transcript_storage: dict[str, bool]
    can_manage: bool


class TicketDetail(ApiModel):
    ticket: TicketItem
    panel: TicketPanel
    messages: list[TicketMessage]
    transcript: TranscriptReference
    outbox: list[dict[str, Any]]


class Transcript(ApiModel):
    ticket: TranscriptTicket
    close_reason: str
    closed_at: int
    closed_by: str
    messages: list[TranscriptMessage]
    attachments: list[TranscriptAttachment]
    feedback_enabled: bool
    feedback_form: TicketForm | None


class TicketFeedback(ApiModel):
    rating: int
    created_at: int


class TicketStatsPanel(ApiModel):
    id: int
    name: str
    total: int
    open: int
    closed: int
    average_resolution_seconds: float | None


class TicketStats(ApiModel):
    summary: dict[str, int | float | None]
    panels: list[TicketStatsPanel]


class TicketExport(ApiModel):
    schema_version: Literal['tueka.ticket-panel.v1'] = Field(alias='schema')
    panel: TicketPanel
    team: TicketTeam | None
    forms: list[TicketForm]
    deployment: TicketDeployment
