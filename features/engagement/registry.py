"""Explicit engagement registration; shared runtimes are registered once."""
from ..contracts import Binding, Category
from .advanced_polls import FEATURE as ADVANCED_POLLS
from .suggestions import FEATURE as SUGGESTIONS
from .minigames import FEATURE as MINIGAMES
from .echo import FEATURE as ECHO
from .calculate import FEATURE as CALCULATE
from .roll import FEATURE as ROLL
from .gemini import FEATURE as GEMINI
from .scheduled_messages import FEATURE as SCHEDULED_MESSAGES
from .starboard import FEATURE as STARBOARD

CATEGORY = Category('engagement', 'nav.engagement', (
    ADVANCED_POLLS,
    SUGGESTIONS,
    MINIGAMES,
    ECHO,
    CALCULATE,
    ROLL,
    GEMINI,
    SCHEDULED_MESSAGES,
    STARBOARD,
))
