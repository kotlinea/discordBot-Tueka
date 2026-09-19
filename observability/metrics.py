"""Small, process-local numeric registry; never accepts payloads or identifiers."""
from collections import defaultdict
from threading import Lock
import math


class Registry:
    def __init__(self):
        self.values = defaultdict(float)
        self.lock = Lock()

    def add(self, name, value=1, **labels):
        if not math.isfinite(value):
            return
        key = name, tuple(sorted(labels.items()))
        with self.lock:
            if key not in self.values and len(self.values) >= 512:
                self.values[('metrics_dropped_series_total', ())] += 1
                return
            self.values[key] += value

    def observe(self, name, seconds, **labels):
        self.add(name + '_sum', seconds, **labels)
        self.add(name + '_count', 1, **labels)

    def snapshot(self):
        with self.lock:
            return [{'name': name, 'labels': dict(labels), 'value': value} for (name, labels), value in self.values.items()]


registry = Registry()
