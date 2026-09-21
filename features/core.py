"""Application entry points, separate from guild feature metadata."""
from .contracts import Binding

CORE_BINDINGS = (
    # General still owns its utility commands until the G3 Cog split.
    Binding('general_bot', 'bot', 'cogs.general:setup', 0),
    Binding('session_api', 'api', 'dashboard.api.session:create_router', 0),
    Binding('guilds_api', 'api', 'dashboard.api.guilds:create_router', 1),
    Binding('modules_api', 'api', 'dashboard.api.modules:create_router', 7),
)
