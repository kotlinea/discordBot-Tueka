---
feature_id: reaction_roles
title: Reaction roles
---

# Reaction roles

Members add or remove emoji reactions to obtain roles. Server managers configure native reaction messages in Dashboard or with `/reactionrole`; `/r` contains aliases.

| Type | On add | On remove |
| --- | --- | --- |
| normal | Grant role | Remove role |
| unique | Switch to one role on the message | Remove role |
| verify | Grant role | Keep role |
| binding | Bind selection | Follow binding restrictions |
| drop | Remove role | No automatic restoration |
| reversed | Remove role | Grant role |
| temp | Grant until expiry | Remove role |

Choose the channel/message and emoji-to-role mappings. Configure per-user limits, per-role capacity, allow/deny roles, locks and linked message groups. The Bot needs Manage Roles and must be above all assigned roles; check channel visibility, reaction and history permissions.

Use addmany/AIO forms for multiple mappings. Inspect configuration and Discord state before using fix, move, purge or selfdestruct. Emoji deletion, managed roles, deleted channels and role hierarchy changes can prevent repair. Reset-binding clears the selected member's binding record. Review the [command reference](../reference/commands) before destructive operations.

Temporary roles last 1 minute to 365 days. Lock pauses both add/remove processing while preserving the previous type. Unique/binding have a fixed selection limit of one. Link groups support normal, unique and temp. Allow/deny modes cannot be combined; denial wins. Emoji and role mappings are unique per message; choose Unicode or available server emoji. Use fixforeign when foreign emoji fail.
