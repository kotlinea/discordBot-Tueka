"""Role effects, atomic assignment commit, and durable compensation."""
import time
import inspect
from typing import Protocol

from discord_io import DiscordFailure
from jobs import LostLease
from jobs.leases import ResourceLease
from .service import ReactionRoleService


class RolePort(Protocol):
    async def member_role_ids(self, guild_id: int, user_id: int) -> set[int]: ...
    async def role(self, guild_id: int, user_id: int, role_id: int, *, add: bool, reason: str) -> None: ...
    async def owns_role_change(self, operation: dict, role_id: int) -> bool: ...
    async def selection_present(self, guild_id: int, channel_id: int, message_id: int, emoji: str, user_id: int) -> bool: ...
    async def role_member_count(self, guild_id: int, role_id: int) -> int: ...


class RoleChangeService:
    def __init__(self, repository, port: RolePort):
        self.repository, self.port = repository, port

    async def apply(self, config: dict, mapping: dict, user_id: int, decision, *, event: str | None = None):
        generation = self.repository.selection_generation(config['id'], mapping['id'], user_id) if event in {'add', 'remove'} else None
        lease = ResourceLease(self.repository.database_url, 'reaction_role_member', f'{config["guild_id"]}:{user_id}')
        entered = False

        async def apply_owned(owned):
            nonlocal entered
            entered = True
            return await self._apply_owned(config, mapping, user_id, decision, owned, event=event)

        try:
            return await lease.run(apply_owned)
        except LostLease as exc:
            if not entered and event in {'add', 'remove'}:
                self.repository.queue_member_reconciliation(config, mapping, user_id, event,
                    selection_generation=generation, competing_owner_token=exc.competing_owner_token)
            raise DiscordFailure(str(exc), retry=True, partial=True) from exc

    async def _apply_owned(self, config, mapping, user_id, decision, lease, *, event=None, removal_job=None):
        current = self.repository.message(config['guild_id'], config['id'])
        if current is None or current['revision'] != config['revision']:
            raise RuntimeError('revision_conflict')
        mapping = next(item for item in current['mappings'] if item['id'] == mapping['id'])
        capacity = ResourceLease(self.repository.database_url, 'reaction_role_capacity', f'{config["guild_id"]}:{mapping["role_id"]}')
        entered = False

        async def apply_with_capacity(owned):
            nonlocal entered
            entered = True
            return await self._apply_capacity_owned(current, mapping, user_id, decision, lease,
                event=event, removal_job=removal_job, capacity=owned)

        try:
            return await capacity.run(apply_with_capacity)
        except LostLease:
            if not entered and event in {'add', 'remove'} and removal_job is None:
                # Member ownership still fences this generation while another
                # member owns the role capacity. An expired member owner must
                # never reserve a removal against its successor's selection.
                self.repository.queue_reaction_removal(current, mapping, user_id, lease=lease, event=event)
            raise

    def _guard_enabled(self, config, mapping, user_id, lease, removal_job, event):
        if not self.repository.settings(config['guild_id']).get('enabled'):
            if removal_job is None and event == 'remove':
                self.repository.queue_reaction_removal(config, mapping, user_id, lease=lease)
            raise DiscordFailure('reaction_roles_disabled', retry=True)

    async def _apply_capacity_owned(self, config, mapping, user_id, decision, lease, *, event=None, removal_job=None, capacity=None):
        if removal_job is not None:
            if not self.repository.reaction_removal_current(removal_job, lease=lease):
                return
        self._guard_enabled(config, mapping, user_id, lease, removal_job, event)
        if event == 'remove' or (event == 'add' and removal_job is not None):
            try:
                present = await self.port.selection_present(
                    config['guild_id'], config['channel_id'], config['message_id'], mapping['emoji'], user_id)
            except DiscordFailure:
                if removal_job is None:
                    self.repository.queue_reaction_removal(config, mapping, user_id, lease=lease)
                raise
            self._guard_enabled(config, mapping, user_id, lease, removal_job, event)
            if present != (event == 'add'):
                return  # Discord's current selection no longer matches this notification.
        self._guard_enabled(config, mapping, user_id, lease, removal_job, event)
        before = await self.port.member_role_ids(config['guild_id'], user_id)
        self._guard_enabled(config, mapping, user_id, lease, removal_job, event)
        source_event = event
        if source_event is None:
            source_event = 'add'
            if config['behavior_type'] not in {'drop', 'verify', 'binding'}:
                removing = decision.operation == 'remove'
                if removing != (config['behavior_type'] == 'reversed'):
                    source_event = 'remove'
        decision = ReactionRoleService(self.repository).decide(
            config, mapping, event=source_event, user_id=user_id, member_role_ids=before)
        if decision.allowed and decision.operation == 'add' and mapping.get('max_members'):
            count = self.port.role_member_count(config['guild_id'], mapping['role_id'])
            if inspect.isawaitable(count):
                count = await count
            self._guard_enabled(config, mapping, user_id, lease, removal_job, event)
            capacity.check()
            decision = ReactionRoleService(self.repository).decide(
                config, mapping, event=source_event, user_id=user_id, member_role_ids=before, role_member_count=count)
        if not decision.allowed:
            raise DiscordFailure(decision.reason)
        if decision.operation == 'none':
            return
        desired = {mapping['role_id']: decision.operation == 'add'}
        if decision.operation == 'add':
            desired.update({int(item['role_id']): False for item in decision.conflicting_assignments if int(item['role_id']) != mapping['role_id']})
        changes = [{'role_id': role_id, 'before': role_id in before, 'after': value}
                   for role_id, value in desired.items()]
        detail = {'config_id': config['id'], 'revision': config['revision'], 'mapping_id': mapping['id'],
            'role_id': mapping['role_id'], 'operation': decision.operation, 'changes': changes,
            'conflicts': decision.conflicting_assignments, 'verify': config['behavior_type'] == 'verify', 'channel_id': config['channel_id'], 'message_id': config.get('message_id'), 'emoji': mapping['emoji'], 'binding': config['behavior_type'] == 'binding',
            'expires_at': int(time.time()) + config['temp_duration_seconds'] if config['behavior_type'] == 'temp' else None}
        operation = self.repository.begin_role_change(config['guild_id'], user_id, detail, lease=lease)
        try:
            for change in changes:
                if change['before'] != change['after']:
                    lease.renew()
                    if capacity is not None:
                        capacity.check()
                    self._guard_enabled(config, mapping, user_id, lease, removal_job, event)
                    if removal_job is not None:
                        self.repository.guard_delivery(removal_job)
                        if not self.repository.reaction_removal_current(removal_job, lease=lease):
                            raise RuntimeError('Removal selection changed')
                    await self.port.role(config['guild_id'], user_id, change['role_id'], add=change['after'],
                                         reason=f'Tueka role operation:{operation["id"]}')
            if removal_job is not None:
                self.repository.guard_delivery(removal_job)
                if not self.repository.reaction_removal_current(removal_job, lease=lease):
                    raise RuntimeError('Removal selection changed')
            self.repository.commit_role_change(operation, lease=lease, **({'removal_job': removal_job} if removal_job else {}))
        except LostLease:
            raise  # An expired owner must not undo its successor's effects.
        except Exception as failure:
            if self.repository.role_change_finished(operation['id']):
                raise
            try:
                await self._recover_owned(operation, lease, held_capacity=capacity)
            except Exception as compensation:
                self.repository.fail_role_compensation(operation['id'], str(compensation), lease=lease)
                raise DiscordFailure('Role compensation requires recovery', partial=True) from failure
            raise

    async def recover(self, operation: dict):
        lease = ResourceLease(self.repository.database_url, 'reaction_role_member', f'{operation["guild_id"]}:{operation["user_id"]}')
        try:
            return await lease.run(lambda owned: self._recover_owned(operation, owned))
        except LostLease as exc:
            raise DiscordFailure(str(exc), retry=True, partial=True) from exc

    async def _recover_owned(self, operation, lease, *, held_capacity=None):
        if self.repository.role_change_finished(operation['id']):
            return
        for change in reversed(operation['detail']['changes']):
            key = f'{operation["guild_id"]}:{change["role_id"]}'
            if held_capacity is not None and held_capacity.key == key:
                await self._recover_role_owned(operation, change, lease, held_capacity)
            else:
                capacity = ResourceLease(self.repository.database_url, 'reaction_role_capacity', key)
                await capacity.run(lambda owned: self._recover_role_owned(operation, change, lease, owned))
        self.repository.finish_role_rollback(operation['id'], lease=lease)

    async def _recover_role_owned(self, operation, change, lease, capacity):
        before = await self.port.member_role_ids(operation['guild_id'], operation['user_id'])
        if (change['role_id'] in before) == change['before']:
            return
        lease.renew()
        if not await self.port.owns_role_change(operation, change['role_id']):
            raise DiscordFailure('Role changed outside this operation or audit proof unavailable', partial=True)
        if change['before']:
            limit = self.repository.role_capacity(operation['guild_id'], change['role_id'])
            if limit is not None:
                count = self.port.role_member_count(operation['guild_id'], change['role_id'])
                if inspect.isawaitable(count):
                    count = await count
                if count >= limit:
                    raise DiscordFailure('Role rollback waiting for capacity', retry=True, partial=True)
        lease.renew()
        capacity.check()
        await self.port.role(operation['guild_id'], operation['user_id'], change['role_id'],
            add=change['before'], reason=f'Tueka role rollback:{operation["id"]}')
