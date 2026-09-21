"""Compose application-scoped feature settings access from explicit factories."""
from features.contracts import Binding
from features.defaults import ModuleSettingsAccess, SettingsAccess
from features.loading import resolve_bindings
from features.registry import FEATURES


def create_settings_access(context) -> dict[str, SettingsAccess]:
    custom = tuple(feature for feature in FEATURES if feature.settings_factory)
    factories = resolve_bindings(tuple(Binding(feature.id, 'api', feature.settings_factory) for feature in custom))
    access = {feature.id: ModuleSettingsAccess(context.guild_settings_repository, feature.id) for feature in FEATURES}
    for feature, factory in zip(custom, factories):
        value = factory(context)
        if not all(callable(getattr(value, name, None)) for name in ('read', 'validate', 'save')):
            raise ValueError(f'Invalid settings access: {feature.id}')
        access[feature.id] = value
    return access
