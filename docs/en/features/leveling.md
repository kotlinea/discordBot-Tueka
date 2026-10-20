---
feature_id: leveling
title: Leveling
---

# Leveling

Text messages and time in voice channels earn XP. Configure the text level-up notification channel. Voice XP has separate enablement, XP per minute, solo participation and muted-user policies.

Configure up to 25 level/role rewards; levels must be unique. The Bot needs Manage Roles and must be above every reward role.

If a reward role could not be granted because of missing permissions, restore those permissions. The next XP award on the same track checks for missing roles at levels already reached. A failed notification preserves recorded XP and does not stop voice XP awards for other members.

Use `/rank`, `/leaderboard`, `/vcrank`, `/vcleaderboard` for text and voice progress. If voice XP does not increase, check voice enablement, channel and solo/mute settings; ask the operator if voice events are unavailable.
