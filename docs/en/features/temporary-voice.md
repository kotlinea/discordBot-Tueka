---
feature_id: temporary_voice
title: Temporary voice channels
---

# Temporary voice channels

Joining the trigger voice channel creates a personal channel and moves the member there. Empty created channels are removed.

While the feature is enabled, the Bot checks for channels that became empty during downtime after startup and approximately every minute. Newly created channels are excluded from these periodic checks for their first 60 seconds.

Select a trigger (required), optional destination category (defaults to the trigger's category), and a name template (empty uses the default). Use the user variables displayed by the editor; names are normalized to Discord limits.

The Bot needs Manage Channels and Move Members. Check the trigger type, category overwrites and Bot role if creation fails.
