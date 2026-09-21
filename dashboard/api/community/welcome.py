"""Welcome settings binding; authorization remains in the modules router."""
from features.defaults import ModuleSettingsAccess
from guild_settings.community.welcome import normalize, validate
from ..context import ApiContext


def create_settings(context: ApiContext) -> ModuleSettingsAccess:
    return ModuleSettingsAccess(context.guild_settings_repository, 'welcome', normalize, validate)
