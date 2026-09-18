from db_support import prepare_database
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import discord
from discord.ext import commands
from cogs.reaction_roles import ReactionRolesCog
from dashboard.discord_api import PERMISSION_BITS, effective_channel_permissions
from reaction_roles.models import ReactionRoleValidationError, normalize_emoji, validate_message
from reaction_roles.repository import ReactionRoleRepository
from reaction_roles.service import ReactionRoleService


def message(*, emoji="😀", role_id=20, behavior="normal", channel_id=10):
    return {
        "name": "Roles",
        "source": "bot",
        "channel_id": channel_id,
        "message_id": None,
        "behavior_type": behavior,
        "locked": False,
        "access_policy": "blacklist",
        "selection_limit": 1 if behavior in {"unique", "binding"} else None,
        "temp_duration_seconds": 60 if behavior == "temp" else None,
        "self_destruct_at": None,
        "enabled": True,
        "embed": {"title": "Choose", "description": "Pick one", "color": "#123456"},
        "mappings": [{"emoji": emoji, "role_id": role_id, "max_members": None}],
        "whitelist_role_ids": [],
        "blacklist_role_ids": [],
        "link_group_id": None,
    }


class ReactionRoleModelTests(unittest.TestCase):
    def test_unicode_emoji_and_custom_emoji_are_normalized(self):
        self.assertEqual(normalize_emoji("❤️")["key"], "unicode:❤️")
        for value in ("👍🏽", "👨‍👩‍👧‍👦", "🇯🇵", "1️⃣", "☕", "⚙️"):
            with self.subTest(value=value):
                self.assertEqual(normalize_emoji(value)["display"], value)
        custom = normalize_emoji("<a:party:123456789012345678>")
        self.assertEqual(custom["key"], "custom:123456789012345678")
        self.assertTrue(custom["animated"])

    def test_non_emoji_unicode_and_multiple_emoji_are_rejected(self):
        for value in ("A", "é", "😀😀", "123", "<:bad:123>"):
            with self.subTest(value=value), self.assertRaises(ReactionRoleValidationError):
                normalize_emoji(value)

    def test_duplicate_roles_and_conflicting_access_are_rejected(self):
        value = message()
        value["mappings"].append({"emoji": "✅", "role_id": 20})
        with self.assertRaises(ReactionRoleValidationError) as duplicate:
            validate_message(value)
        self.assertEqual(duplicate.exception.path, "mappings.1.role_id")
        value = message()
        value.update({"whitelist_role_ids": [30], "blacklist_role_ids": [40]})
        with self.assertRaises(ReactionRoleValidationError) as conflict:
            validate_message(value)
        self.assertEqual(conflict.exception.code, "access_conflict")
        value = message()
        value.update({"access_policy": "whitelist", "blacklist_role_ids": [40]})
        with self.assertRaises(ReactionRoleValidationError) as mismatch:
            validate_message(value)
        self.assertEqual(mismatch.exception.code, "access_policy_conflict")

    def test_type_constraints_are_typed(self):
        value = message(behavior="temp")
        value["temp_duration_seconds"] = 59
        with self.assertRaises(ReactionRoleValidationError):
            validate_message(value)
        value = message(behavior="binding")
        value["link_group_id"] = 1
        with self.assertRaises(ReactionRoleValidationError):
            validate_message(value)


class ReactionRoleRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = ReactionRoleRepository(prepare_database(Path(self.temp.name) / "rr.sqlite3", self.addCleanup))
        self.service = ReactionRoleService(self.repo)

    def tearDown(self):
        self.temp.cleanup()

    def test_revision_outbox_and_mapping_identity(self):
        saved = self.service.create(1, message(), actor_id=2)
        self.assertTrue(self.repo.settings(1)["enabled"])
        self.assertEqual(saved["status"], "pending")
        mapping_id = saved["mappings"][0]["id"]
        saved["name"] = "Updated"
        updated = self.service.update(1, saved["id"], saved, saved["revision"], actor_id=2)
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(updated["mappings"][0]["id"], mapping_id)
        with self.assertRaises(RuntimeError):
            self.service.update(1, saved["id"], saved, saved["revision"], actor_id=2)
        claimed = [self.repo.outbox_jobs.claim("test").payload for _ in range(2)]
        self.assertEqual([item["action"] for item in claimed], ["publish", "sync"])

    def test_explicit_disable_is_not_overwritten_by_new_configuration(self):
        self.repo.save_settings(1, {"enabled": False}, 0)
        self.service.create(1, message())
        self.assertFalse(self.repo.settings(1)["enabled"])

    def test_active_panel_repairs_missing_settings_row(self):
        self.service.create(1, message())
        with self.repo.connection() as connection:
            connection.execute("DELETE FROM reaction_role_settings WHERE guild_id=1")
        self.assertTrue(self.repo.settings(1)["enabled"])

    def test_binding_receipt_survives_role_removal_until_reset(self):
        saved = self.service.create(1, message(behavior="binding"))
        mapping = saved["mappings"][0]
        self.repo.activate_assignment(1, saved["id"], mapping["id"], 99, mapping["role_id"], None, binding=True)
        self.repo.deactivate_assignment(saved["id"], mapping["id"], 99)
        denied = self.service.decide(saved, mapping, event="add", user_id=99, member_role_ids=set())
        self.assertFalse(denied.allowed)
        self.assertTrue(self.repo.reset_binding(saved["id"], 99))
        self.assertTrue(self.service.decide(saved, mapping, event="add", user_id=99, member_role_ids=set()).allowed)

    def test_blacklist_precedes_whitelist_and_remove_is_always_allowed(self):
        saved = self.service.create(1, {**message(), "access_policy": "blacklist", "blacklist_role_ids": [40]})
        mapping = saved["mappings"][0]
        # Runtime remains defensive for legacy rows that predate the single-policy model.
        saved["whitelist_role_ids"] = [30]
        denied = self.service.decide(saved, mapping, event="add", user_id=1, member_role_ids={30, 40})
        self.assertFalse(denied.allowed)
        removed = self.service.decide(saved, mapping, event="remove", user_id=1, member_role_ids={40})
        self.assertTrue(removed.allowed)
        self.assertEqual(removed.operation, "remove")

    def test_access_policy_is_persisted_and_outbox_claim_is_exclusive(self):
        saved = self.service.create(1, {**message(), "access_policy": "whitelist", "whitelist_role_ids": [30]})
        self.assertEqual(saved["access_policy"], "whitelist")
        self.assertEqual(saved["whitelist_role_ids"], [30])
        first = self.repo.outbox_jobs.claim("worker-a")
        second = self.repo.outbox_jobs.claim("worker-b")
        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_link_group_is_global_unique_and_rejects_incompatible_types(self):
        first = self.service.create(1, message(role_id=20))
        second = self.service.create(1, message(emoji="✅", role_id=21, channel_id=11))
        group = self.repo.create_link_group(1, "Colors", [first["id"], second["id"]])
        linked_first = self.repo.message(1, first["id"])
        linked_second = self.repo.message(1, second["id"])
        self.repo.activate_assignment(1, linked_first["id"], linked_first["mappings"][0]["id"], 8, 20, None)
        decision = self.service.decide(linked_second, linked_second["mappings"][0], event="add", user_id=8, member_role_ids={20})
        self.assertEqual(decision.conflicting_assignments[0]["message_config_id"], linked_first["id"])
        self.repo.dissolve_link_group(1, group["id"])
        verify = self.service.create(1, message(emoji="🔒", role_id=22, behavior="verify", channel_id=12))
        with self.assertRaises(ValueError):
            self.repo.create_link_group(1, "Invalid", [first["id"], verify["id"]])

    def test_temp_schedule_recovery_and_audit_retention(self):
        saved = self.service.create(1, message(behavior="temp"))
        mapping = saved["mappings"][0]
        self.repo.activate_assignment(1, saved["id"], mapping["id"], 7, 20, int(time.time()) - 1)
        due = [self.repo.schedule_jobs.claim("worker").payload]
        self.assertEqual(due[0]["kind"], "temp_role")
        self.repo.set_discord_message(saved["id"], 123)
        self.repo.delete_message(1, saved["id"], recoverable=True)
        self.assertIsNotNone(self.repo.recovery(1, 123))
        self.assertTrue(self.repo.events(1))


class DiscordPermissionTests(unittest.TestCase):
    def test_channel_overwrites_are_applied_in_discord_order(self):
        base = PERMISSION_BITS["view_channel"] | PERMISSION_BITS["add_reactions"] | PERMISSION_BITS["manage_messages"]
        permissions = effective_channel_permissions(
            1,
            99,
            {1, 20},
            base,
            [
                {"id": "1", "type": 0, "allow": "0", "deny": str(PERMISSION_BITS["add_reactions"])},
                {"id": "20", "type": 0, "allow": str(PERMISSION_BITS["add_reactions"]), "deny": str(PERMISSION_BITS["manage_messages"])},
                {"id": "99", "type": 1, "allow": str(PERMISSION_BITS["manage_messages"]), "deny": "0"},
            ],
        )
        self.assertTrue(permissions & PERMISSION_BITS["add_reactions"])
        self.assertTrue(permissions & PERMISSION_BITS["manage_messages"])


class ReactionRoleCogTests(unittest.IsolatedAsyncioTestCase):
    async def test_custom_emoji_must_belong_to_the_current_guild(self):
        interaction = SimpleNamespace(guild=SimpleNamespace(emojis=[SimpleNamespace(id=123456789012345678)]))
        ReactionRolesCog._validate_guild_emojis(interaction, {"mappings": [{"emoji": "<:party:123456789012345678>"}]})
        with self.assertRaises(ReactionRoleValidationError):
            ReactionRolesCog._validate_guild_emojis(interaction, {"mappings": [{"emoji": "<:other:223456789012345678>"}]})

    async def test_publish_retry_reuses_the_message_created_before_reaction_failure(self):
        config = {**message(), "id": 7, "created_at": 1000, "guild_id": 1, "message_id": None, "mappings": [{"emoji": "✅", "role_id": 20}]}
        item = {"id": 8, "guild_id": 1, "message_config_id": 7, "action": "publish", "payload": {}}

        class FakeMessage:
            author = SimpleNamespace(id=999)
            id = 900
            failures = 1

            async def edit(self, **_kwargs):
                return self

            async def add_reaction(self, _emoji):
                if self.failures:
                    self.failures -= 1
                    raise discord.HTTPException(SimpleNamespace(status=503, reason="Unavailable"), "reaction failed")

        fake_message = FakeMessage()

        class FakeChannel:
            send_count = 0

            async def send(self, **_kwargs):
                self.send_count += 1
                return fake_message

            async def fetch_message(self, message_id):
                self.assert_message_id = message_id
                return fake_message

        channel = FakeChannel()

        class FakeRepository:
            def message(self, _guild_id, _config_id): return config
            def set_discord_message(self, _config_id, message_id, status="active", error=None):
                config["message_id"] = message_id
                config["status"] = status
            def set_delivery_status(self, _config_id, status, error=None): config["status"] = status

        guild = SimpleNamespace(id=1, get_channel=lambda _channel_id: channel, get_channel_or_thread=lambda _channel_id: channel)
        cog = object.__new__(ReactionRolesCog)
        cog.bot = SimpleNamespace(get_guild=lambda _guild_id: guild)
        cog.repository = FakeRepository()
        from reaction_roles.discord_adapter import DiscordReactionRoleAdapter
        from reaction_roles.delivery import ReactionRoleDeliveryService
        cog.bot.user = SimpleNamespace(id=999)
        cog.delivery = ReactionRoleDeliveryService(cog.repository, DiscordReactionRoleAdapter(cog.bot))
        cog.owner = "test-worker"

        with patch("cogs.reaction_roles.discord.TextChannel", FakeChannel), patch("cogs.reaction_roles.discord.Thread", FakeChannel):
            outcome = await ReactionRolesCog._process_outbox_item(cog, item)
            self.assertTrue(outcome.retry)
            self.assertEqual(config["message_id"], 900)
            self.assertEqual(channel.send_count, 1)
            await ReactionRolesCog._process_outbox_item(cog, item)
            self.assertEqual(channel.send_count, 1)
            self.assertEqual(config["status"], "active")

    async def test_move_commit_persists_cleanup_and_replay_does_not_repeat_move(self):
        from reaction_roles.delivery import ReactionRoleDeliveryService
        from jobs import Outcome
        from unittest.mock import AsyncMock
        with tempfile.TemporaryDirectory() as directory:
            repo = ReactionRoleRepository(prepare_database(Path(directory) / 'move.db', self.addCleanup))
            config = ReactionRoleService(repo).create(1, message())
            repo.set_discord_message(config['id'], 900)
            publication = repo.outbox_jobs.claim('worker')
            repo.outbox_jobs.finish(publication, Outcome())
            port = SimpleNamespace(add_reactions=AsyncMock(return_value='external'), delete=AsyncMock())
            delivery = ReactionRoleDeliveryService(repo, port)
            item = {'guild_id': 1, 'message_config_id': config['id'], 'action': 'move',
                    'payload': {'revision': config['revision'], 'channel_id': 11, 'message_id': 901}}
            self.assertIsNone((await delivery.outbox(item)).error)
            self.assertIsNone((await delivery.outbox(item)).error)
            port.add_reactions.assert_awaited_once()
            cleanup = repo.outbox_jobs.claim('restarted')
            self.assertEqual(cleanup.payload['action'], 'delete')
            self.assertIsNone(cleanup.payload['message_config_id'])
            self.assertEqual(cleanup.payload['payload']['message_id'], 900)
            await delivery.outbox(cleanup.payload)
            port.delete.assert_awaited_once_with(1, 10, 900)

    async def test_expiry_fetch_failure_does_not_confirm_member_absence(self):
        from reaction_roles.discord_adapter import DiscordReactionRoleAdapter
        from discord_io import DiscordFailure
        from unittest.mock import AsyncMock
        guild = SimpleNamespace(get_member=lambda _: None, get_role=lambda _: object(),
            fetch_member=AsyncMock(side_effect=discord.HTTPException(
                SimpleNamespace(status=503, reason='Unavailable'), 'fetch failed')))
        adapter = DiscordReactionRoleAdapter(SimpleNamespace(get_guild=lambda _: guild))
        with self.assertRaises(DiscordFailure) as failed:
            await adapter.role(1, 2, 3, add=False, reason='expired')
        self.assertTrue(failed.exception.retry)

    async def test_command_groups_load_without_discord_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            bot = commands.Bot(command_prefix="/", intents=discord.Intents.none())
            bot.settings = SimpleNamespace(database_url=prepare_database(Path(directory) / "rr.sqlite3", self.addCleanup), reaction_role_max_mappings_per_message=20)
            async with bot:
                await bot.load_extension("cogs.reaction_roles")
                root = bot.tree.get_command("reactionrole")
                short = bot.tree.get_command("r")
                self.assertIsNotNone(root)
                self.assertIsNotNone(short)
                self.assertTrue({"create", "add", "addmany", "remove", "purge", "modify", "whitelist", "blacklist", "link", "manage", "channel", "aio"} <= {item.name for item in root.commands})
                self.assertTrue({"add", "addmany", "remove", "show", "fix", "normal", "unique", "verify", "binding", "drop", "reversed", "temp", "lock", "unlock", "aio", "aiou", "aiov", "aioi"} <= {item.name for item in short.commands})


if __name__ == "__main__":
    unittest.main()
