"""Explicit social registration; shared runtimes are registered once."""
from ..contracts import Binding, Category
from .youtube_updates import FEATURE as YOUTUBE_UPDATES
from .twitch_updates import FEATURE as TWITCH_UPDATES
from .tiktok_updates import FEATURE as TIKTOK_UPDATES
from .x_updates import FEATURE as X_UPDATES
from .instagram_updates import FEATURE as INSTAGRAM_UPDATES

CATEGORY = Category('social', 'nav.social', (
    YOUTUBE_UPDATES,
    TWITCH_UPDATES,
    TIKTOK_UPDATES,
    X_UPDATES,
    INSTAGRAM_UPDATES,
), bindings=(
    Binding('social_delivery', 'bot', 'cogs.social.delivery:setup', 15),
    Binding('social_api', 'api', 'dashboard.api.social.providers:create_router', 3),
    Binding('social_worker', 'worker', 'social.worker:main', 0),
))

