"""Leveling settings rules; authentication and resource checks stay shared."""
from features.defaults import ModuleSettingsAccess


def validate(enabled, settings):
    if enabled and settings.get('voice_enabled') and not settings.get('voice_notification_channel_id'):
        raise ValueError('voice_notification_channel_id')


def additional_permissions(settings):
    return ('manage_roles',) if settings.get('text_role_rewards') or settings.get('voice_role_rewards') else ()


def create_settings(context):
    return ModuleSettingsAccess(context.guild_settings_repository, 'leveling',
                                validate=validate, additional_permissions=additional_permissions)
