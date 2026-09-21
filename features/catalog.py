"""Validate declarations without importing any of their runtime targets."""
from types import MappingProxyType
import re

from .contracts import Binding, Category, Process

_ID = re.compile(r'^[a-z][a-z0-9_]*$')
_TARGET = re.compile(r'^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*$')


class Registry:
    def __init__(self, categories: tuple[Category, ...], core: tuple[Binding, ...] = ()):
        category_ids = set()
        features = {}
        bindings = list(core)
        for category in categories:
            if not _ID.fullmatch(category.id) or category.id in category_ids or not category.title_key:
                raise ValueError(f'Invalid or duplicate category: {category.id}')
            category_ids.add(category.id)
            bindings.extend(category.bindings)
            for feature in category.features:
                if not _ID.fullmatch(feature.id) or feature.id in features:
                    raise ValueError(f'Invalid or duplicate feature: {feature.id}')
                if feature.category != category.id:
                    raise ValueError(f'Unregistered category for {feature.id}: {feature.category}')
                if len(set(feature.fields)) != len(feature.fields) or not set(feature.required_fields) <= set(feature.fields):
                    raise ValueError(f'Invalid fields: {feature.id}')
                if feature.dashboard and (not all((feature.title_key, feature.description_key, feature.icon, *feature.copy_ja))
                                          or not feature.docs_path.startswith('/docs/')):
                    raise ValueError(f'Incomplete dashboard metadata: {feature.id}')
                features[feature.id] = feature
                if feature.settings_factory is not None and not _TARGET.fullmatch(feature.settings_factory):
                    raise ValueError(f'Invalid settings factory: {feature.id}')
                bindings.extend(feature.bindings)
        for feature in features.values():
            seen = {feature.id}
            parent = feature.parent
            while parent is not None:
                if parent not in features:
                    raise ValueError(f'Unknown parent for {feature.id}: {parent}')
                if parent in seen:
                    raise ValueError(f'Cyclic feature parent: {feature.id}')
                seen.add(parent)
                if features[parent].category != feature.category:
                    raise ValueError(f'Parent belongs to another category: {feature.id}')
                parent = features[parent].parent
        ids, targets, docs = set(), set(), set()
        for binding in bindings:
            if not _ID.fullmatch(binding.id) or binding.id in ids:
                raise ValueError(f'Invalid or duplicate binding: {binding.id}')
            if binding.process not in ('bot', 'api', 'worker') or not _TARGET.fullmatch(binding.target):
                raise ValueError(f'Invalid binding target: {binding.id}')
            key = (binding.process, binding.target)
            if key in targets:
                raise ValueError(f'Duplicate runtime target: {binding.target}')
            ids.add(binding.id)
            targets.add(key)
        for feature in features.values():
            if feature.dashboard:
                if feature.docs_path in docs:
                    raise ValueError(f'Duplicate feature documentation: {feature.docs_path}')
                docs.add(feature.docs_path)
        self.categories = tuple(categories)
        self.features = tuple(sorted(features.values(), key=lambda value: value.order))
        self.by_id = MappingProxyType(features)
        self.bindings = tuple(sorted(bindings, key=lambda value: value.order))

    def for_process(self, process: Process) -> tuple[Binding, ...]:
        if process not in ('bot', 'api', 'worker'):
            raise ValueError(f'Unknown process: {process}')
        return tuple(binding for binding in self.bindings if binding.process == process)
