"""Controlled authorization boundary probe; run in canonical test-python only."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from moderation.contracts import GuildRef, MemberRef
from moderation.discord_adapter import DiscordModerationAdapter
from moderation.service import ModerationService

class AuthorizationProbe(unittest.IsolatedAsyncioTestCase):
    async def test_permission_revoked_while_waiting_for_member_lease(self):
        reached, release = asyncio.Event(), asyncio.Event()
        permissions = SimpleNamespace(ban_members=True, administrator=False)
        target = SimpleNamespace(id=2, top_role=1, guild_permissions=SimpleNamespace(administrator=False))
        moderator = SimpleNamespace(id=3, top_role=5, guild_permissions=permissions)
        guild = SimpleNamespace(id=1, owner_id=99, me=SimpleNamespace(top_role=10, guild_permissions=SimpleNamespace(ban_members=True)),
            get_member=lambda ident: {2:target, 3:moderator}.get(ident), ban=AsyncMock())
        port = DiscordModerationAdapter(SimpleNamespace(get_guild=lambda ident:guild))
        repository = MagicMock(database_url='unused')
        repository.case_execution.return_value = None
        repository.create_moderation_event.return_value = 1
        repository.add_case.return_value = 1
        service = ModerationService(port, repository, MagicMock())
        class Lease:
            def __init__(self, *args): pass
            async def run(self, callback):
                reached.set()
                await release.wait()
                return await callback(self)
        with patch('moderation.service.ResourceLease', Lease):
            pending = asyncio.create_task(service.apply_case(GuildRef(1), MemberRef(2,1), 'ban', 'probe', 3,
                notify=False, actor=MemberRef(3,1), source='automod'))
            await reached.wait()
            permissions.ban_members = False
            release.set()
            try:
                await pending
            except PermissionError:
                pass
        self.assertEqual(guild.ban.await_count, 0, 'Revoked moderator permission must prevent Discord ban after lease wait')

class ActorBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self):
        self.permissions = SimpleNamespace(ban_members=False, kick_members=False, moderate_members=False, administrator=False)
        self.moderator = SimpleNamespace(id=3, top_role=5, guild_permissions=self.permissions)
        self.target = SimpleNamespace(id=2, top_role=1, guild_permissions=SimpleNamespace(administrator=False))
        self.guild = SimpleNamespace(id=1, owner_id=99, me=SimpleNamespace(top_role=10, guild_permissions=SimpleNamespace(administrator=True)),
            get_member=lambda ident: {2:self.target, 3:self.moderator, 99:SimpleNamespace(id=99,top_role=0,guild_permissions=self.permissions)}.get(ident))
        return DiscordModerationAdapter(SimpleNamespace(get_guild=lambda ident:self.guild))

    async def test_permissions_owner_admin_guild_and_absent_unban(self):
        port = self.adapter()
        for action in ('ban', 'tempban', 'softban', 'kick', 'timeout', 'untimeout', 'unban'):
            with self.subTest(action=action):
                self.assertIsNotNone(port.manageable(MemberRef(3,1), MemberRef(2,1), action))
        self.assertIsNotNone(port.manageable(MemberRef(3,9), MemberRef(2,1), 'unban'))
        self.assertIsNotNone(port.manageable(MemberRef(8,1), MemberRef(2,1), 'unban'))
        self.permissions.administrator = True
        self.assertIsNone(port.manageable(MemberRef(3,1), MemberRef(7,1), 'unban'))
        self.permissions.administrator = False
        self.assertIsNone(port.manageable(MemberRef(99,1), MemberRef(7,1), 'unban'))
        self.assertIsNone(port.manageable(None, MemberRef(2,1), 'ban'))
        self.assertIsNone(port.manageable(None, MemberRef(7,1), 'unban'))
        self.permissions.administrator = True
        self.target.top_role = 5
        self.assertIsNotNone(port.manageable(MemberRef(3,1), MemberRef(2,1), 'ban'))

    async def test_only_manual_infraction_propagates_actor_to_member_operation(self):
        from moderation.contracts import ActionContext
        port, repository, settings = MagicMock(), MagicMock(), MagicMock()
        service = ModerationService(port, repository, settings)
        service.apply_case = AsyncMock(return_value=1)
        actor, target = MemberRef(3,1), MemberRef(2,1)
        context = ActionContext(GuildRef(1), target, actor=actor)
        for family in ('infraction', 'automod', 'anti_spam', 'anti_raid'):
            with self.subTest(family=family):
                await service.execute_actions(context, {'family':family,'actions':[{'type':'ban'}]}, 'reason', 1, {})
                self.assertEqual(service.apply_case.await_args.kwargs['actor'], actor if family == 'infraction' else None)
