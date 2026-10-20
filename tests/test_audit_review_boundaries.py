import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from cogs.moderation.audit_log import AuditLogCog


class AuditDeduplicationBoundaries(unittest.IsolatedAsyncioTestCase):
    async def test_ban_and_member_remove_do_not_emit_an_extra_leave(self):
        cog = AuditLogCog.__new__(AuditLogCog)
        cog._recent_actions = {}
        cog._channel = Mock(return_value=object())
        cog._send = AsyncMock()
        cog._recent_audit = AsyncMock(return_value=SimpleNamespace(user=SimpleNamespace(mention='moderator'), reason='synthetic'))
        guild = SimpleNamespace(id=1)
        member = SimpleNamespace(id=2, guild=guild, mention='synthetic member')
        await cog.on_member_ban(guild, member)
        await cog.on_member_remove(member)
        self.assertEqual(cog._send.await_count, 1)
        self.assertIn('BAN', cog._send.call_args.args[2])

    async def test_previously_claimed_kick_does_not_fall_through_to_leave(self):
        cog = AuditLogCog.__new__(AuditLogCog)
        cog._recent_actions = {}
        cog._channel = Mock(return_value=object())
        cog._send = AsyncMock()
        cog._recent_audit = AsyncMock(side_effect=[None, SimpleNamespace(user=SimpleNamespace(mention='moderator'), reason='synthetic')])
        cog._claim_action(1, 'kick', 2)
        await cog.on_member_remove(SimpleNamespace(id=2, guild=SimpleNamespace(id=1)))
        cog._send.assert_not_awaited()

    async def test_member_remove_first_then_ban_keeps_one_ban_record(self):
        cog = AuditLogCog.__new__(AuditLogCog)
        cog._recent_actions = {}
        cog._channel = Mock(return_value=object())
        cog._send = AsyncMock()
        cog._recent_audit = AsyncMock(return_value=SimpleNamespace(user=SimpleNamespace(mention='moderator'), reason='synthetic'))
        guild = SimpleNamespace(id=1)
        member = SimpleNamespace(id=2, guild=guild)
        await cog.on_member_remove(member)
        await cog.on_member_ban(guild, member)
        self.assertEqual(cog._send.await_count, 1)
        self.assertIn('BAN', cog._send.call_args.args[2])

    async def test_ordinary_departure_still_emits_leave(self):
        cog = AuditLogCog.__new__(AuditLogCog)
        cog._recent_actions = {}
        cog._channel = Mock(return_value=object())
        cog._send = AsyncMock()
        cog._recent_audit = AsyncMock(return_value=None)
        await cog.on_member_remove(SimpleNamespace(id=2, guild=SimpleNamespace(id=1)))
        self.assertEqual(cog._send.await_count, 1)
        self.assertIn('退会', cog._send.call_args.args[2])

