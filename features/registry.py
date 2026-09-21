"""The only category list. Runtime implementations are imported on demand."""
from .catalog import Registry
from .community.registry import CATEGORY as COMMUNITY
from .engagement.registry import CATEGORY as ENGAGEMENT
from .moderation.registry import CATEGORY as MODERATION
from .social.registry import CATEGORY as SOCIAL
from .core import CORE_BINDINGS
from .contracts import Feature

REGISTRY = Registry((COMMUNITY, ENGAGEMENT, MODERATION, SOCIAL), CORE_BINDINGS)
FEATURES = tuple(feature for feature in REGISTRY.features if feature.dashboard)
FEATURE_BY_ID = {feature.id: feature for feature in FEATURES}
BOT_EXTENSIONS = tuple(binding.target.partition(':')[0] for binding in REGISTRY.for_process('bot'))


def get_feature(feature_id: str) -> Feature:
    try:
        return FEATURE_BY_ID[feature_id]
    except KeyError as exc:
        raise ValueError('Unknown feature') from exc


def japanese_copy(feature_id: str) -> tuple[str, str]:
    return get_feature(feature_id).copy_ja
