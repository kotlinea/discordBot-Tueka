"""Default settings access. Authentication and resource checks stay in adapters."""
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Protocol

Settings = dict[str, Any]
Normalizer = Callable[[Settings], Settings]


def validate_settings(enabled: bool, settings: Settings) -> None:
    """Default has no feature-specific combination rules."""


def additional_permissions(settings: Settings) -> tuple[str, ...]:
    return ()


class SettingsResources(Protocol):
    """Resource details available to API-owned settings validation."""
    def channel_ids(self, *types: int) -> set[int]: ...
    def channel_permissions(self, channel_id: int) -> int: ...


def validate_resources(enabled: bool, settings: Settings, resources: SettingsResources) -> None:
    """Default settings need only the router's resource membership checks."""


class ModuleStore(Protocol):
    def get_module(self, guild_id: int, module_id: str) -> Settings: ...
    def set_module(self, guild_id: int, module_id: str, *, enabled: bool,
                   settings: Settings, expected_revision: int | None) -> Settings: ...


class SettingsAccess(Protocol):
    """A dedicated store may also provide an optional validate_resources hook."""
    def read(self, guild_id: int) -> Settings: ...
    def validate(self, enabled: bool, settings: Settings) -> None: ...
    def additional_permissions(self, settings: Settings) -> tuple[str, ...]: ...
    def save(self, guild_id: int, *, enabled: bool, settings: Settings,
             expected_revision: int | None) -> Settings: ...


@dataclass(frozen=True)
class ModuleSettingsAccess:
    store: ModuleStore
    feature_id: str
    normalize: Normalizer = deepcopy
    validate: Callable[[bool, Settings], None] = validate_settings
    additional_permissions: Callable[[Settings], tuple[str, ...]] = additional_permissions
    validate_resources: Callable[[bool, Settings, SettingsResources], None] = validate_resources

    def read(self, guild_id: int) -> Settings:
        return self.from_module(self.store.get_module(guild_id, self.feature_id))

    def from_module(self, module: Settings) -> Settings:
        value = deepcopy(module)
        return {**value, 'settings': self.normalize(value['settings'])}

    def save(self, guild_id: int, *, enabled: bool, settings: Settings,
             expected_revision: int | None) -> Settings:
        return self.store.set_module(guild_id, self.feature_id, enabled=enabled,
                                     settings=self.normalize(deepcopy(settings)),
                                     expected_revision=expected_revision)


class DedicatedStore(Protocol):
    def settings(self, guild_id: int) -> Settings: ...
    def save_settings(self, guild_id: int, value: Settings, expected_revision: int | None) -> Settings: ...


@dataclass(frozen=True)
class RepositorySettingsAccess:
    """Use a domain-owned settings repository without changing its transaction."""
    store: DedicatedStore | None
    validate: Callable[[bool, Settings], None] = validate_settings
    additional_permissions: Callable[[Settings], tuple[str, ...]] = additional_permissions
    validate_resources: Callable[[bool, Settings, SettingsResources], None] = validate_resources

    @staticmethod
    def _module(value: Settings) -> Settings:
        return {'enabled': value['enabled'], 'revision': value['revision'], 'settings': value}

    def read(self, guild_id: int) -> Settings:
        value = self.store.settings(guild_id) if self.store else {'enabled': False, 'revision': 0}
        return self._module(deepcopy(value))

    def save(self, guild_id: int, *, enabled: bool, settings: Settings,
             expected_revision: int | None) -> Settings:
        if self.store is None:
            raise RuntimeError('settings_store_unavailable')
        value = self.store.save_settings(guild_id, {**deepcopy(settings), 'enabled': enabled}, expected_revision)
        return self._module(value)
