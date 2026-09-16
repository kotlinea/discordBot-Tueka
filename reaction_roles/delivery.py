"""Durable publication and expiry decisions, with Discord I/O injected."""
from typing import Protocol

from discord_io import DiscordFailure
from jobs import Outcome, LostLease
from jobs.leases import ResourceLease
from .repository import ReactionRoleRepository


class ReactionRolePort(Protocol):
    async def publish(self, config: dict, *, recover: bool = False) -> int: ...
    async def add_reactions(self, guild_id: int, channel_id: int, message_id: int, emojis: list[str], *, foreign: bool = False) -> str: ...
    async def delete(self, guild_id: int, channel_id: int, message_id: int) -> None: ...
    async def remove_selection(self, guild_id: int, channel_id: int, message_id: int, emoji: str, user_id: int) -> None: ...
    async def role(self, guild_id: int, user_id: int, role_id: int, *, add: bool, reason: str) -> None: ...


class ReactionRoleDeliveryService:
    def __init__(self, repository: ReactionRoleRepository, port: ReactionRolePort):
        self.repository, self.port = repository, port

    async def outbox(self, item: dict) -> Outcome:
        config = self.repository.message(int(item['guild_id']), int(item['message_config_id'])) if item.get('message_config_id') else None
        payload, guild_id = item['payload'], int(item['guild_id'])
        try:
            if item['action'] == 'clear_selection':
                await self.port.remove_selection(guild_id, int(payload['channel_id']), int(payload['message_id']), payload['emoji'], int(payload['user_id']))
                return Outcome()
            if item['action'] == 'delete':
                target = config or payload
                if target.get('message_id') and target.get('source') == 'bot':
                    await self.port.delete(guild_id, target['channel_id'], target['message_id'])
                return Outcome()
            if config is None:
                raise DiscordFailure('message_unavailable')
            emojis = [mapping['emoji'] for mapping in config['mappings']]
            if item['action'] == 'move':
                revision = int(payload.get('revision', config['revision']))
                target_channel, target_message = int(payload['channel_id']), int(payload['message_id'])
                if config['revision'] == revision + 1 and (config['channel_id'], config.get('message_id')) == (target_channel, target_message):
                    return Outcome()
                if revision != config['revision']:
                    return Outcome('revision_conflict')
                source = await self.port.add_reactions(guild_id, target_channel, target_message, emojis)
                try:
                    self.repository.move_message(guild_id, config['id'], target_channel, target_message, source, revision)
                except Exception:
                    self.repository.audit(guild_id, config['id'], 'move_commit_failed', 'partial',
                        details={'channel_id': target_channel, 'message_id': target_message})
                    raise
                return Outcome()
            recover = config.get('status') == 'publishing'
            self.repository.set_delivery_status(config['id'], 'publishing')
            message_id = await self.port.publish(config, recover=recover)
            self.repository.set_discord_message(config['id'], message_id, status='publishing')
            await self.port.add_reactions(guild_id, config['channel_id'], message_id, emojis, foreign=bool(payload.get('foreign')))
            self.repository.set_discord_message(config['id'], message_id)
            return Outcome()
        except DiscordFailure as exc:
            if config:
                self.repository.set_delivery_status(config['id'], 'publishing' if exc.partial else 'pending' if exc.retry else 'failed', str(exc))
            return Outcome(str(exc), retry=exc.retry or exc.partial)
        except (ValueError, RuntimeError) as exc:
            return Outcome(str(exc), retry=str(exc) != 'revision_conflict')

    async def schedule(self, item: dict) -> Outcome:
        if item['kind'] == 'temp_role':
            lease = ResourceLease(self.repository.database_path, 'reaction_role_member', f'{item["guild_id"]}:{item["user_id"]}')
            try:
                return await lease.run(lambda owned: self._schedule_owned(item, owned))
            except LostLease as exc:
                return Outcome(str(exc), retry=True)
        return await self._schedule_owned(item)

    async def _schedule_owned(self, item, lease=None):
        config = self.repository.message(int(item['guild_id']), int(item['message_config_id'])) if item.get('message_config_id') else None
        try:
            if item['kind'] == 'self_destruct' and config and config['source'] == 'bot':
                self.repository.queue_action(item['guild_id'], config['id'], 'delete',
                    {'channel_id': config['channel_id'], 'message_id': config.get('message_id'), 'source': config['source']})
                self.repository.delete_message(item['guild_id'], config['id'], recoverable=False)
            elif item['kind'] == 'temp_role' and config:
                active = next((assignment for assignment in self.repository.assignments(item['user_id'], config_id=config['id'])
                               if assignment['mapping_id'] == item['mapping_id'] and assignment.get('expires_at') == item['due_at']), None)
                if active is None:
                    return Outcome()
                if any(operation['user_id'] == item['user_id'] for operation in self.repository.pending_role_changes(item['guild_id'])):
                    return Outcome('Role compensation pending', retry=True)
                mapping = next((m for m in config['mappings'] if m['id'] == item['mapping_id']), None)
                if mapping:
                    await self.port.role(item['guild_id'], item['user_id'], mapping['role_id'], add=False, reason='Temporary Reaction Role expired')
                    self.repository.deactivate_assignment(config['id'], mapping['id'], item['user_id'], lease=lease)
            return Outcome()
        except DiscordFailure as exc:
            return Outcome(str(exc), retry=exc.retry)
