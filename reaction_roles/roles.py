"""Role effects, atomic assignment commit, and durable compensation."""
import time
from typing import Protocol

from discord_io import DiscordFailure
from jobs import LostLease
from jobs.leases import ResourceLease


class RolePort(Protocol):
    async def member_role_ids(self, guild_id: int, user_id: int) -> set[int]: ...
    async def role(self, guild_id: int, user_id: int, role_id: int, *, add: bool, reason: str) -> None: ...
    async def owns_role_change(self, operation: dict, role_id: int) -> bool: ...


class RoleChangeService:
    def __init__(self, repository, port: RolePort):
        self.repository, self.port = repository, port

    async def apply(self, config: dict, mapping: dict, user_id: int, decision):
        lease = ResourceLease(self.repository.database_path, 'reaction_role_member', f'{config["guild_id"]}:{user_id}')
        try:
            return await lease.run(lambda owned: self._apply_owned(config, mapping, user_id, decision, owned))
        except LostLease as exc:
            raise DiscordFailure(str(exc), retry=True, partial=True) from exc

    async def _apply_owned(self, config, mapping, user_id, decision, lease):
        before = await self.port.member_role_ids(config['guild_id'], user_id)
        if decision.operation == 'add':
            if set(config.get('blacklist_role_ids', [])) & before or (config.get('whitelist_role_ids') and not set(config['whitelist_role_ids']) & before):
                raise DiscordFailure('Member access changed')
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
                    await self.port.role(config['guild_id'], user_id, change['role_id'], add=change['after'],
                                         reason=f'Tueka role operation:{operation["id"]}')
            self.repository.commit_role_change(operation, lease=lease)
        except LostLease:
            raise  # An expired owner must not undo its successor's effects.
        except Exception as failure:
            if self.repository.role_change_finished(operation['id']):
                raise
            try:
                await self._recover_owned(operation, lease)
            except Exception as compensation:
                self.repository.fail_role_compensation(operation['id'], str(compensation), lease=lease)
                raise DiscordFailure('Role compensation requires recovery', partial=True) from failure
            raise

    async def recover(self, operation: dict):
        lease = ResourceLease(self.repository.database_path, 'reaction_role_member', f'{operation["guild_id"]}:{operation["user_id"]}')
        try:
            return await lease.run(lambda owned: self._recover_owned(operation, owned))
        except LostLease as exc:
            raise DiscordFailure(str(exc), retry=True, partial=True) from exc

    async def _recover_owned(self, operation, lease):
        if self.repository.role_change_finished(operation['id']):
            return
        before = await self.port.member_role_ids(operation['guild_id'], operation['user_id'])
        for change in reversed(operation['detail']['changes']):
            if (change['role_id'] in before) != change['before']:
                lease.renew()
                if not await self.port.owns_role_change(operation, change['role_id']):
                    raise DiscordFailure('Role changed outside this operation or audit proof unavailable', partial=True)
                await self.port.role(operation['guild_id'], operation['user_id'], change['role_id'],
                                     add=change['before'], reason=f'Tueka role rollback:{operation["id"]}')
        self.repository.finish_role_rollback(operation['id'], lease=lease)
