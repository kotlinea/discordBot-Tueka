"""Ticket-specific channel, role, permission and emoji requirements."""
from __future__ import annotations
from typing import Any
from dashboard.api.resources import GuildResources

class TicketResources:

    def __init__(self, discord):
        self.discord = discord

    async def validate_ticket_resources(self, guild_id: int, value: dict[str, Any]) -> None:
        resources = await GuildResources.fetch(self.discord, guild_id)
        channel_types = {key: int(item['type']) for key, item in resources.channels.items()}
        role_ids = resources.role_ids
        for key in ('log_channel_id', 'transcript_channel_id', 'thread_parent_channel_id', 'staff_notification_channel_id', 'notification_channel_id', 'channel_id'):
            if value.get(key) and channel_types.get(int(value[key])) != 0:
                raise ValueError(key)
        for key in ('category_id', 'awaiting_category_id'):
            if value.get(key) and channel_types.get(int(value[key])) != 4:
                raise ValueError(key)
        for key in ('role_ids', 'required_role_ids', 'mention_role_ids'):
            if any((int(item) not in role_ids for item in value.get(key, []))):
                raise ValueError(key)
        if any((int(item.get('role_id', 0)) not in role_ids for item in value.get('access_rules', []))):
            raise ValueError('access_rules')
        required: set[str] = set()
        if value.get('category_id'):
            required.update({'manage_channels', 'send_messages', 'read_message_history', 'manage_messages'})
        if value.get('thread_parent_channel_id'):
            required.update({'manage_threads', 'create_private_threads', 'send_messages_in_threads', 'read_message_history'})
        if value.get('channel_id'):
            required.update({'send_messages', 'embed_links'})
        missing = resources.missing_permissions(required)
        if missing:
            raise ValueError('bot_permissions:' + ','.join(sorted(missing)))

    async def validate_ticket_bundle_resources(self, guild_id: int, bundle: dict[str, Any]) -> None:
        panel, deployment = (bundle['panel'], bundle['deployment'])
        await self.validate_ticket_resources(guild_id, {**panel, **deployment})
        emoji = str(panel.get('button', {}).get('emoji') or '')
        if emoji.startswith('<'):
            match = __import__('re').fullmatch('<a?:[A-Za-z0-9_]{2,32}:(\\d+)>', emoji)
            emoji_ids = {int(item['id']) for item in await self.discord.guild_emojis(guild_id, use_cache=False)}
            if not match or int(match.group(1)) not in emoji_ids:
                raise ValueError('button_emoji')
