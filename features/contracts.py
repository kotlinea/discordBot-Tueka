"""Immutable registration data, independent of Discord, HTTP and persistence."""
from dataclasses import dataclass
from typing import Literal

Process = Literal['bot', 'api', 'worker']


@dataclass(frozen=True)
class Binding:
    id: str
    process: Process
    target: str  # Explicit module:callable, resolved only by its process.
    order: int = 0


@dataclass(frozen=True)
class Feature:
    id: str
    category: str
    title_key: str = ''
    description_key: str = ''
    icon: str = ''
    docs_path: str = ''
    fields: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()
    required_bot_permissions: tuple[str, ...] = ()
    parent: str | None = None
    copy_ja: tuple[str, str] = ('', '')
    order: int = 0
    dashboard: bool = True
    bindings: tuple[Binding, ...] = ()
    settings_factory: str | None = None  # API-scoped SettingsAccess factory.


@dataclass(frozen=True)
class Category:
    id: str
    title_key: str
    features: tuple[Feature, ...]
    bindings: tuple[Binding, ...] = ()  # Shared runtimes have one owner here.
