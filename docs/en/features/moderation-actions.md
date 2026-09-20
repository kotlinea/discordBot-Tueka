---
feature_id: moderation_actions
title: Moderation actions
---

# Moderation actions

Available actions include warn, timeout/untimeout, kick, ban/unban, temporary ban, softban, message/purge/reaction removal, channel lock/unlock and server lockdown/release. Permissions, role hierarchy and target state are checked immediately before execution. High-impact Dashboard actions require target-name confirmation.

Use `/mod` for moderation actions. You can also use `/warn`, `/timeout`, `/kick`, `/ban` and `/clear` for their corresponding actions. See the [command reference](../reference/commands) for arguments and permissions.

Softban bans then unbans. If only the first step succeeds, inspect the case and action log before repairing the state; do not assume the member was unbanned.
