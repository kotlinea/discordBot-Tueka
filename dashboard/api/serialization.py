"""JSON-safe Discord resource identifiers."""
from __future__ import annotations
from typing import Any

def _resource_kind(key: str) -> tuple[str, bool] | None:
    if key == 'temp_voice_trigger_id' or key.endswith(('channel_id', 'category_id')):
        return ('channel', False)
    if key.endswith(('channel_ids', 'category_ids')):
        return ('channel', True)
    if key.endswith('role_id'):
        return ('role', False)
    if key.endswith('role_ids'):
        return ('role', True)
    return None

def _serialize_resource_ids(settings: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(settings)
    for key, value in settings.items():
        kind = _resource_kind(key)
        if kind is None:
            continue
        if kind[1]:
            serialized[key] = [str(item) for item in value] if value else []
        else:
            serialized[key] = str(value) if value not in (None, '') else None
    return serialized

def _normalize_resource_ids(settings: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(settings)
    for key, value in settings.items():
        kind = _resource_kind(key)
        if kind is None:
            continue
        if kind[1]:
            normalized[key] = [int(item) for item in value] if value else []
        else:
            normalized[key] = int(value) if value not in (None, '') else None
    return normalized

def _serialize_rule_resource_ids(rule: dict[str, Any]) -> dict[str, Any]:
    serialized = dict(rule)
    for section in ('trigger_config', 'conditions', 'exemptions'):
        serialized[section] = _serialize_resource_ids(dict(rule.get(section) or {}))
    serialized['actions'] = [_serialize_resource_ids(dict(action)) for action in rule.get('actions', [])]
    return serialized
