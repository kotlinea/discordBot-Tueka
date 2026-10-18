---
title: Server Insights
feature_id: insights
---

# Server Insights

Guild managers can view observed messages, joins, leaves, and voice connection time by UTC day. The chart and table show the same selected reporting period.

## Start collection

1. Open **Collection settings** and select up to 25 channels for message and voice metrics.
2. Enable **Count joins and leaves** if needed.
3. Set retention to 1–365 days, enable collection, and save. An empty channel selection records no message or voice activity.

Collection starts with new events while the Bot is connected. Bots, webhooks, NSFW channels, private threads, and the AFK channel are excluded. Public threads follow the selected text or forum parent. Message bodies, attachments, display names, and audio content are never stored.

## Read the report

Select up to 90 days inside the retention window. **Not observed** differs from zero. Observed seconds measure continuous Bot observation; days with outages or downtime do not represent complete daily activity. Voice time measures connection duration rather than speech, summed across participants.

Intervals spanning a restart, disconnect, disabled collection, or collection settings change are not filled in. Observation gaps longer than 90 seconds are excluded. Membership events without a known join timestamp, messages or join notifications more than 90 seconds late, and delayed messages created before collection or during an observation gap are excluded. Historical messages are not fetched.

Retained reports remain readable with collection OFF. A daily record expires the configured number of days after its UTC day begins; later updates do not extend that expiry. Shortening retention removes older aggregates during maintenance. Deduplication identifiers last at most one day, and voice participant IDs last only during observation before expiry cleanup. Cleanup also runs while collection is OFF. Increasing retention cannot restore deleted data.
