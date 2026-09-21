"""Explicit moderation registration; shared runtimes are registered once."""
from ..contracts import Binding, Category
from .moderation import FEATURE as MODERATION
from .automod import FEATURE as AUTOMOD
from .anti_spam import FEATURE as ANTI_SPAM
from .anti_raid import FEATURE as ANTI_RAID
from .infractions import FEATURE as INFRACTIONS
from .moderation_actions import FEATURE as MODERATION_ACTIONS
from .moderation_logs import FEATURE as MODERATION_LOGS
from .audit_log import FEATURE as AUDIT_LOG
from .trust_score import FEATURE as TRUST_SCORE

CATEGORY = Category('moderation', 'nav.moderation', (
    MODERATION,
    AUTOMOD,
    ANTI_SPAM,
    ANTI_RAID,
    INFRACTIONS,
    MODERATION_ACTIONS,
    MODERATION_LOGS,
    AUDIT_LOG,
    TRUST_SCORE,
), bindings=(
    Binding('moderation_runtime', 'bot', 'cogs.automod:setup', 6),
    Binding('moderation_api', 'api', 'dashboard.api.moderation:create_router', 8),
))

