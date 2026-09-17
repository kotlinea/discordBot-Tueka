"""Ticket response serialization."""
from __future__ import annotations
from typing import Any

def ticket_ids(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop('encrypted_content', None)
    result.pop('form_answers_json', None)
    result.pop('payload_json', None)
    singular = ('guild_id', 'channel_id', 'message_id', 'category_id', 'thread_parent_channel_id', 'staff_notification_channel_id', 'log_channel_id', 'transcript_channel_id', 'discord_container_id', 'parent_channel_id', 'opener_id', 'claimed_by', 'closed_by', 'notification_channel_id', 'awaiting_category_id', 'previous_channel_id', 'previous_message_id', 'awaiting_return_category_id')
    plural = ('role_ids', 'user_ids', 'admin_user_ids', 'required_role_ids', 'mention_role_ids', 'mention_user_ids')
    for key in singular:
        if key in result:
            result[key] = str(result[key]) if result[key] not in (None, '') else None
    for key in plural:
        if key in result:
            result[key] = [str(item) for item in result.get(key, [])]
    return result

def ticket_bundle_payload(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    if result.get('panel'):
        result['panel'] = ticket_ids(result['panel'])
        result['panel']['access_rules'] = [{**rule, 'role_id': str(rule['role_id'])} for rule in result['panel'].get('access_rules', [])]
    if result.get('deployment'):
        result['deployment'] = ticket_ids(result['deployment'])
    result['deployments'] = [ticket_ids(item) for item in result.get('deployments', [])]
    return result
