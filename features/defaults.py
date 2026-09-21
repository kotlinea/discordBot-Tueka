"""Default settings access. Authentication and resource checks stay in adapters."""
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Protocol

Settings = dict[str, Any]
Normalizer = Callable[[Settings], Settings]


def validate_settings(enabled: bool, settings: Settings) -> None:
    """Default has no feature-specific combination rules."""


class ModuleStore(Protocol):
    def get_module(self, guild_id: int, module_id: str) -> Settings: ...
    def set_module(self, guild_id: int, module_id: str, *, enabled: bool,
                   settings: Settings, expected_revision: int | None) -> Settings: ...


class SettingsAccess(Protocol):
    """A feature may supply a dedicated store with this same contract."""
    def read(self, guild_id: int) -> Settings: ...
    def validate(self, enabled: bool, settings: Settings) -> None: ...
    def save(self, guild_id: int, *, enabled: bool, settings: Settings,
             expected_revision: int | None) -> Settings: ...


@dataclass(frozen=True)
class ModuleSettingsAccess:
    store: ModuleStore
    feature_id: str
    normalize: Normalizer = deepcopy
    validate: Callable[[bool, Settings], None] = validate_settings

    def read(self, guild_id: int) -> Settings:
        value = deepcopy(self.store.get_module(guild_id, self.feature_id))
        return {**value, 'settings': self.normalize(value['settings'])}

    def save(self, guild_id: int, *, enabled: bool, settings: Settings,
             expected_revision: int | None) -> Settings:
        return self.store.set_module(guild_id, self.feature_id, enabled=enabled,
                                     settings=self.normalize(deepcopy(settings)),
                                     expected_revision=expected_revision)
