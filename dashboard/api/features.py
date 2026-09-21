"""Feature registry responses shared by overview and settings routes."""
from __future__ import annotations
from typing import Any
from dashboard.discord_api import ADMINISTRATOR, PERMISSION_BITS
from features.registry import japanese_copy
from .serialization import _serialize_resource_ids

class FeaturePresenter:

    def __init__(self, context):
        self.context = context

    def feature_payload(self, guild_id: int, feature: Any, bot_permissions: int) -> dict[str, Any]:
        if feature.id in {'tickets', 'reaction_roles'}:
            repository = self.context.ticket_repository if feature.id == 'tickets' else self.context.reaction_role_repository
            value = repository.settings(guild_id) if repository else {'enabled': False, 'revision': 0}
            module = {'enabled': value['enabled'], 'revision': value['revision'], 'settings': value}
        else:
            module = self.context.feature_settings[feature.id].read(guild_id)
        missing = [] if bot_permissions & ADMINISTRATOR else [name for name in feature.required_bot_permissions if not bot_permissions & PERMISSION_BITS[name]]
        title, description = japanese_copy(feature.id)
        return {'id': feature.id, 'category': feature.category, 'parent': feature.parent, 'docs_path': feature.docs_path, 'title': title, 'description': description, 'fields': list(feature.fields), 'required_fields': list(feature.required_fields), 'required_bot_permissions': list(feature.required_bot_permissions), 'enabled': module['enabled'], 'settings': _serialize_resource_ids(module['settings']), 'revision': module['revision'], 'missing_permissions': missing}
