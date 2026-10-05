---
feature_id: moderation_actions
title: Moderation actions
---

# Moderation actions

Available actions include warn, timeout/untimeout, kick, ban/unban, temporary ban, softban, message/purge/reaction removal, channel lock/unlock and server lockdown/release. Permissions, role hierarchy and target state are checked immediately before execution. For high-impact Dashboard actions, confirm by entering the target user ID or server ID shown on the screen.

Use `/mod` for moderation actions. You can also use `/warn`, `/timeout`, `/kick`, `/ban` and `/clear` for their corresponding actions. See the [command reference](../reference/commands) for arguments and permissions.

Softban bans then unbans. If only the first step succeeds, inspect the case and action log before repairing the state; do not assume the member was unbanned.
