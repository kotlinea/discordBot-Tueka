"""A pure settings model, independent of runtime feature registration."""
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

@dataclass(frozen=True)
class SettingsModel:
    normalize: Callable = deepcopy
    defaults: Callable = dict

    def read(self, values):
        return self.normalize(self.defaults() if values is None else values)
