import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

import discord
from discord.ext import commands
from reaction_roles.models import ReactionRoleValidationError, normalize_emoji, validate_message
from reaction_roles.repository import ReactionRoleRepository
from reaction_roles.service import ReactionRoleService


def message(*, emoji="é", role_id=20, behavior="normal", channel_id=10):
    return {
        "name": "Roles",
        "source": "bot",
        "channel_id": channel_id,
        "message_id": None,
        "behavior_type": behavior,
        "locked": False,
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
    def test_unicode_is_normalized_and_custom_emoji_uses_id(self):
        self.assertEqual(normalize_emoji("e\u0301")["key"], normalize_emoji("é")["key"])
        custom = normalize_emoji("<a:party:123456789012345678>")
        self.assertEqual(custom["key"], "custom:123456789012345678")
        self.assertTrue(custom["animated"])

    def test_duplicate_roles_and_conflicting_access_are_rejected(self):
        value = message()
        value["mappings"].append({"emoji": "✅", "role_id": 20})
        with self.assertRaises(ReactionRoleValidationError) as duplicate:
            validate_message(value)
        self.assertEqual(duplicate.exception.path, "mappings.1.role_id")
        value = message()
        value.update({"whitelist_role_ids": [30], "blacklist_role_ids": [30]})
        with self.assertRaises(ReactionRoleValidationError):
            validate_message(value)

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
        self.repo = ReactionRoleRepository(Path(self.temp.name) / "rr.sqlite3")
        self.service = ReactionRoleService(self.repo)

    def tearDown(self):
        self.temp.cleanup()

    def test_revision_outbox_and_mapping_identity(self):
        saved = self.service.create(1, message(), actor_id=2)
        self.assertEqual(saved["status"], "pending")
        mapping_id = saved["mappings"][0]["id"]
        saved["name"] = "Updated"
        updated = self.service.update(1, saved["id"], saved, saved["revision"], actor_id=2)
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(updated["mappings"][0]["id"], mapping_id)
        with self.assertRaises(RuntimeError):
            self.service.update(1, saved["id"], saved, saved["revision"], actor_id=2)
        claimed = self.repo.claim_outbox("test")
        self.assertEqual([item["action"] for item in claimed], ["publish", "sync"])

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
        saved = self.service.create(1, {**message(), "whitelist_role_ids": [30], "blacklist_role_ids": [40]})
        mapping = saved["mappings"][0]
        denied = self.service.decide(saved, mapping, event="add", user_id=1, member_role_ids={30, 40})
        self.assertFalse(denied.allowed)
        removed = self.service.decide(saved, mapping, event="remove", user_id=1, member_role_ids={40})
        self.assertTrue(removed.allowed)
        self.assertEqual(removed.operation, "remove")

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
        due = self.repo.due_schedules("worker")
        self.assertEqual(due[0]["kind"], "temp_role")
        self.repo.set_discord_message(saved["id"], 123)
        self.repo.delete_message(1, saved["id"], recoverable=True)
        self.assertIsNotNone(self.repo.recovery(1, 123))
        self.assertTrue(self.repo.events(1))


class ReactionRoleCogTests(unittest.IsolatedAsyncioTestCase):
    async def test_command_groups_load_without_discord_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            bot = commands.Bot(command_prefix="/", intents=discord.Intents.none())
            bot.settings = SimpleNamespace(database_path=Path(directory) / "rr.sqlite3", reaction_role_max_mappings_per_message=20)
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
