"""Feature registry responses shared by overview and settings routes."""
from __future__ import annotations
from collections.abc import Iterable
from typing import Any
from dashboard.discord_api import ADMINISTRATOR, PERMISSION_BITS
from features.registry import japanese_copy
from features.defaults import ModuleSettingsAccess
from features.contracts import Feature
from .serialization import _serialize_resource_ids

class FeaturePresenter:

    def __init__(self, context):
        self.context = context

    def feature_payload(self, guild_id: int, feature: Any, bot_permissions: int) -> dict[str, Any]:
        module = self.context.feature_settings[feature.id].read(guild_id)
        return self._payload(feature, bot_permissions, module)

    def feature_payloads(self, guild_id: int, features: Iterable[Feature], bot_permissions: int) -> list[dict[str, Any]]:
        features = tuple(features)
        store = self.context.guild_settings_repository
        standard = {}
        for feature in features:
            access = self.context.feature_settings[feature.id]
            # Custom factories and subclasses keep their own read contract.
            if type(access) is ModuleSettingsAccess and access.store is store and not feature.settings_factory:
                standard[feature.id] = access
        modules = store.get_modules(guild_id, (access.feature_id for access in standard.values()))
        payloads = []
        for feature in features:
            if feature.id in standard:
                access = standard[feature.id]
                module = access.from_module(modules[access.feature_id])
                payloads.append(self._payload(feature, bot_permissions, module))
            else:
                payloads.append(self.feature_payload(guild_id, feature, bot_permissions))
        return payloads

    @staticmethod
    def _payload(feature: Any, bot_permissions: int, module: dict[str, Any]) -> dict[str, Any]:
        missing = [] if bot_permissions & ADMINISTRATOR else [name for name in feature.required_bot_permissions if not bot_permissions & PERMISSION_BITS[name]]
        title, description = japanese_copy(feature.id)
        return {'id': feature.id, 'category': feature.category, 'parent': feature.parent, 'docs_path': feature.docs_path, 'title': title, 'description': description, 'fields': list(feature.fields), 'required_fields': list(feature.required_fields), 'required_bot_permissions': list(feature.required_bot_permissions), 'enabled': module['enabled'], 'settings': _serialize_resource_ids(module['settings']), 'revision': module['revision'], 'missing_permissions': missing}
