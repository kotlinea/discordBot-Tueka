"""Additional permission required for member audit events."""
from features.defaults import ModuleSettingsAccess


def additional_permissions(settings):
    return ('view_audit_log',) if settings.get('log_member') else ()


def create_settings(context):
    return ModuleSettingsAccess(context.guild_settings_repository, 'audit_log',
                                additional_permissions=additional_permissions)
