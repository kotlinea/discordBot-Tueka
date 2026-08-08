"""Single source of truth for dashboard feature modules."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Feature:
    id: str
    category: str
    title_key: str
    description_key: str
    icon: str
    fields: tuple[str, ...] = ()


FEATURES = (
    Feature("welcome", "community", "feature.welcome", "feature.welcome.description", "users", ("welcome_channel_id", "default_role_id")),
    Feature("leveling", "community", "feature.leveling", "feature.leveling.description", "chart", ()),
    Feature("audit_log", "moderation", "feature.audit_log", "feature.audit_log.description", "clipboard", ("management_channel_id",)),
    Feature("moderation", "moderation", "feature.moderation", "feature.moderation.description", "shield", ()),
)
FEATURE_BY_ID = {feature.id: feature for feature in FEATURES}


def get_feature(feature_id: str) -> Feature:
    try:
        return FEATURE_BY_ID[feature_id]
    except KeyError as exc:
        raise ValueError("Unknown feature") from exc
