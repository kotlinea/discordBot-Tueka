"""Resolve selected-process factories. No global service cache or auto-discovery."""
from importlib import import_module
from inspect import iscoroutinefunction
from typing import Callable

from .contracts import Binding


def resolve_bindings(bindings: tuple[Binding, ...]) -> tuple[Callable, ...]:
    """Preflight all targets before any factory is called."""
    resolved = []
    seen = set()
    for binding in bindings:
        if binding.target in seen:
            raise ValueError(f'Duplicate runtime target: {binding.target}')
        seen.add(binding.target)
        module, separator, name = binding.target.partition(':')
        if not separator or not module or not name:
            raise ValueError(f'Invalid binding target: {binding.target}')
        try:
            factory = getattr(import_module(module), name)
        except (ImportError, AttributeError) as exc:
            raise ValueError(f'Cannot resolve binding {binding.id}: {binding.target}') from exc
        if not callable(factory):
            raise ValueError(f'Binding is not callable: {binding.target}')
        if binding.process in ('bot', 'worker') and not iscoroutinefunction(factory):
            raise ValueError(f'Binding must be async: {binding.target}')
        if binding.process == 'api' and iscoroutinefunction(factory):
            raise ValueError(f'API factory must be synchronous: {binding.target}')
        resolved.append(factory)
    return tuple(resolved)


def validate_extensions(extensions: tuple[str, ...]) -> None:
    resolve_bindings(tuple(Binding(f'extension_{index}', 'bot', f'{module}:setup')
                           for index, module in enumerate(extensions)))
