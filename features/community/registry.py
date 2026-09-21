"""Explicit community registration; shared runtimes are registered once."""
from ..contracts import Binding, Category
from .welcome import FEATURE as WELCOME
from .autorole import FEATURE as AUTOROLE
from .leveling import FEATURE as LEVELING
from .reaction_roles import FEATURE as REACTION_ROLES
from .live_stats import FEATURE as LIVE_STATS
from .temporary_voice import FEATURE as TEMPORARY_VOICE
from .tickets import FEATURE as TICKETS

CATEGORY = Category('community', 'nav.community', (
    WELCOME,
    AUTOROLE,
    LEVELING,
    REACTION_ROLES,
    LIVE_STATS,
    TEMPORARY_VOICE,
    TICKETS,
), bindings=(
    Binding('community_bot', 'bot', 'cogs.community:setup', 8),
))

