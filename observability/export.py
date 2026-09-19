"""Prometheus-compatible metrics with fixed operational dimensions."""
import json
import math


def render(snapshot):
    lines = []

    def metric(name, value, **labels):
        value = float(value)
        if not math.isfinite(value):
            return
        suffix = '{' + ','.join(key + '=' + json.dumps(str(value)) for key, value in sorted(labels.items())) + '}' if labels else ''
        lines.append('tueka_' + name + suffix + ' ' + str(value))

    metric('database_up', 1)
    for key, value in snapshot['database'].items():
        metric('postgres_' + key, value)
    for name, item in snapshot['services'].items():
        metric('service_ready', item['ready'], service=name)
        metric('heartbeat_age_seconds', item['age_seconds'], service=name)
        for record in item['metrics']:
            metric(record['name'], record['value'], service=name, **record['labels'])
    for name, values in snapshot['queues'].items():
        for key, value in values.items():
            metric('queue_' + key, value, queue=name)
    for key, value in snapshot['thresholds'].items():
        metric('threshold_' + key, value)
    return '\n'.join(lines) + '\n'
