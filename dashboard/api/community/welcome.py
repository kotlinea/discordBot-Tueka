"""Welcome settings binding; authorization remains in the modules router."""
from dashboard.discord_api import ADMINISTRATOR, PERMISSION_BITS
from features.defaults import ModuleSettingsAccess, SettingsResources
from guild_settings.community.welcome import normalize, validate
from ..context import ApiContext


def validate_resources(enabled: bool, settings: dict, resources: SettingsResources) -> None:
    if not enabled:
        return
    for event in ('welcome', 'leave'):
        if not settings.get(f'{event}_enabled'):
            continue
        channel_id = int(settings[f'{event}_channel_id'])
        if channel_id not in resources.channel_ids(0):
            raise ValueError('welcome_channel_type')
        permissions = resources.channel_permissions(channel_id)
        required = ['view_channel', 'send_messages']
        if settings.get(f'{event}_format') == 'embed':
            required.append('embed_links')
        if not permissions & ADMINISTRATOR and any(not permissions & PERMISSION_BITS[name] for name in required):
            raise ValueError('welcome_channel_permissions')


def create_settings(context: ApiContext) -> ModuleSettingsAccess:
    return ModuleSettingsAccess(context.guild_settings_repository, 'welcome', normalize, validate,
                                validate_resources=validate_resources)
