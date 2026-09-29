---
feature_id: automod
title: AutoMod
---

# AutoMod

Inspect message content and combine removal, warnings, notifications and timeout. Use [Anti-Spam](./anti-spam) for rate windows. Configure banned terms as keyword rules in Dashboard.

| Trigger | Configuration and behavior |
| --- | --- |
| keyword | Terms, wildcards and allowed words; Unicode normalization |
| regex | Bounded regular expressions; validated on save |
| domain | Allow/deny domains; normalized IDN and complete domain boundaries |
| discord_invite | Discord invite links |
| safe_browsing | URL checks; unavailable checks fail open |
| phishing_link | Display/target mismatch and phishing indicators |
| caps | Uppercase ratio and minimum length |
| emoji_sticker_rate | Emoji/sticker count per message or time window |
| media_only | Detect posts without attachments or embeds in selected channels |
| honeypot | Detect any post in selected channels |

Whitelist mode includes selected roles/users/channels/categories; blacklist mode excludes them. Conflicting allow/deny entries are rejected. Actions execute in order: removal, warning/points, public/DM/moderator notice, log, timeout, kick, ban or temporary ban. A failed action does not prevent other possible actions; inspect their results.

Use the variables displayed in the template editor. Preview regex matches, nonmatches and timeout behavior; avoid ambiguous nested repetitions. For sanctions based on accumulated points, enable [Infractions](./infractions) and configure thresholds and actions.

See [the rule workflow](../dashboard/moderation-rules.md) for creation, duplication and bulk state changes.
