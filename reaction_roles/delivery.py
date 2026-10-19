"""Durable publication and expiry decisions, with Discord I/O injected."""
from typing import Protocol

from discord_io import DiscordFailure
from jobs import Outcome, LostLease
from jobs.leases import ResourceLease
from .repository import ReactionRoleRepository
from .roles import RoleChangeService
from .service import ReactionRoleService


class ReactionRolePort(Protocol):
    async def member_role_ids(self, guild_id: int, user_id: int) -> set[int]: ...
    async def owns_role_change(self, operation: dict, role_id: int) -> bool: ...
    async def selection_present(self, guild_id: int, channel_id: int, message_id: int, emoji: str, user_id: int) -> bool: ...
    async def role_member_count(self, guild_id: int, role_id: int) -> int: ...
    async def publish(self, config: dict, *, recover: bool = False) -> int: ...
    async def add_reactions(self, guild_id: int, channel_id: int, message_id: int, emojis: list[str], *, foreign: bool = False) -> str: ...
    async def delete(self, guild_id: int, channel_id: int, message_id: int) -> None: ...
    async def remove_selection(self, guild_id: int, channel_id: int, message_id: int, emoji: str, user_id: int) -> None: ...
    async def role(self, guild_id: int, user_id: int, role_id: int, *, add: bool, reason: str) -> None: ...


class ReactionRoleDeliveryService:
    def __init__(self, repository: ReactionRoleRepository, port: ReactionRolePort):
        self.repository, self.port = repository, port

    def _guard_outbox(self, item):
        if item.get('_lease'):
            self.repository.guard_delivery(item)

    async def _clear_selection(self, item, lease):
        if not self.repository.cleanup_current(item):
            return Outcome()
        lease.renew()
        self._guard_outbox(item)
        payload = item['payload']
        await self.port.remove_selection(int(item['guild_id']),int(payload['channel_id']),int(payload['message_id']),payload['emoji'],int(payload['user_id']))
        self._guard_outbox(item)
        lease.check()
        return Outcome()

    async def outbox(self, item: dict) -> Outcome:
        config = self.repository.message(int(item['guild_id']), int(item['message_config_id'])) if item.get('message_config_id') else None
        payload, guild_id = item['payload'], int(item['guild_id'])
        owned = {'job': item} if item.get('_lease') else {}
        try:
            if item['action'] in {'reconcile_remove', 'reconcile_add', 'reconcile_selection'}:
                if config is None:
                    return Outcome()
                mapping = next((m for m in config['mappings'] if m['id'] == payload['mapping_id']), None)
                if mapping is None:
                    return Outcome()
                member = ResourceLease(self.repository.database_url, 'reaction_role_member', f'{guild_id}:{payload["user_id"]}')
                role_service = RoleChangeService(self.repository, self.port)
                event = payload['event'] if item['action'] == 'reconcile_selection' else 'add' if item['action'] == 'reconcile_add' else 'remove'
                decision = ReactionRoleService(self.repository).decide(config, mapping, event=event,
                    user_id=payload['user_id'], member_role_ids=set())
                await member.run(lambda lease: role_service._apply_owned(config, mapping, payload['user_id'], decision,
                    lease, event=event, removal_job=item))
                return Outcome()
            if item['action'] == 'clear_selection':
                member = ResourceLease(self.repository.database_url, 'reaction_role_member', f'{guild_id}:{payload["user_id"]}')
                return await member.run(lambda lease: self._clear_selection(item, lease))
            if item['action'] == 'delete':
                target = config or payload
                if target.get('message_id') and target.get('source') == 'bot':
                    self._guard_outbox(item)
                    await self.port.delete(guild_id, target['channel_id'], target['message_id'])
                    self._guard_outbox(item)
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
                self._guard_outbox(item)
                source = await self.port.add_reactions(guild_id, target_channel, target_message, emojis)
                try:
                    self.repository.move_message(guild_id, config['id'], target_channel, target_message, source, revision, **owned)
                except LostLease:
                    raise
                except Exception:
                    self.repository.audit(guild_id, config['id'], 'move_commit_failed', 'partial',
                        details={'channel_id': target_channel, 'message_id': target_message})
                    raise
                return Outcome()
            recover = config.get('status') == 'publishing'
            self.repository.set_delivery_status(config['id'], 'publishing', **owned)
            self._guard_outbox(item)
            message_id = await self.port.publish(config, recover=recover)
            self.repository.set_discord_message(config['id'], message_id, status='publishing', **owned)
            self._guard_outbox(item)
            await self.port.add_reactions(guild_id, config['channel_id'], message_id, emojis, foreign=bool(payload.get('foreign')))
            self.repository.set_discord_message(config['id'], message_id, **owned)
            return Outcome()
        except LostLease as exc:
            return Outcome(str(exc), retry=True)
        except DiscordFailure as exc:
            if item['action'] in {'reconcile_remove', 'reconcile_add', 'reconcile_selection'}:
                return Outcome(str(exc), retry=True)
            if config:
                self.repository.set_delivery_status(config['id'], 'publishing' if exc.partial else 'pending' if exc.retry else 'failed', str(exc), **owned)
            return Outcome(str(exc), retry=exc.retry or exc.partial)
        except (ValueError, RuntimeError) as exc:
            return Outcome(str(exc), retry=str(exc) != 'revision_conflict' and 'reconciliation required' not in str(exc))

    async def schedule(self, item: dict) -> Outcome:
        if item['kind'] == 'temp_role':
            lease = ResourceLease(self.repository.database_url, 'reaction_role_member', f'{item["guild_id"]}:{item["user_id"]}')
            try:
                return await lease.run(lambda owned: self._schedule_owned(item, owned))
            except LostLease as exc:
                return Outcome(str(exc), retry=True)
        return await self._schedule_owned(item)

    async def _schedule_owned(self, item, lease=None):
        try:
            if item.get('scheduled_for') is None:
                return Outcome('Original schedule time unavailable; reconciliation required')
            if item['kind'] == 'self_destruct' and item.get('message_config_id'):
                self.repository.consume_self_destruct(item['guild_id'], item['message_config_id'], item['scheduled_for'], item)
            elif item['kind'] == 'temp_role':
                expiry = self.repository.temporary_expiry(item, lease=lease)
                if expiry is None:
                    return Outcome()
                if any(operation['user_id'] == item['user_id'] for operation in self.repository.pending_role_changes(item['guild_id'])):
                    return Outcome('Role compensation pending', retry=True)
                if expiry['remove_role']:
                    lease.renew()
                    self.repository.guard_delivery(item, schedule=True)
                    await self.port.role(item['guild_id'], item['user_id'], expiry['role_id'], add=False, reason='Temporary Reaction Role expired')
                self.repository.finish_temporary_expiry(item, expiry, lease=lease)
            return Outcome()
        except DiscordFailure as exc:
            return Outcome(str(exc), retry=exc.retry)
        except ValueError as exc:
            return Outcome(str(exc))
