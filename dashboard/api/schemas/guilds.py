"""Guild overview schema."""
from .base import ApiModel
from .common import Feature, Resources
from .moderation import ModerationOverview


class GuildOverview(ApiModel):
    guild_id: str
    features: list[Feature]
    resources: Resources
    moderation: ModerationOverview
