---
feature_id: anti_raid
title: Anti-Raid
---

# Anti-Raid

Detect join/leave bursts, recently created account ratios and activity immediately after joining. Triggers are `join_rate`, `leave_rate`, `new_account_ratio` and `new_member_activity`.

Raid state survives restarts. End it through configured exit conditions or administrator action. Combine administrator notices, timeout/kick/ban, channel locks and server lockdown. Lockdown retains previous channel overwrites for expiry or manual release; later administrator changes are treated as conflicts rather than overwritten.

The Bot needs Manage Channels for locks, and Moderate Members/Kick Members/Ban Members for the corresponding sanctions. Role hierarchy still applies.

See [the rule workflow](../dashboard/moderation-rules.md) for creation, duplication and bulk state changes.
