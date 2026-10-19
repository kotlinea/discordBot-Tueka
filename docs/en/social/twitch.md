---
feature_id: twitch_updates
---

# Twitch

Register the Twitch account and select a destination for stream notifications. Save and wait for account resolution. Configure the event template and preview before enabling role mentions.

Resolved accounts remain monitored by user identity after a username change. If a different stream starts between checks, the previous stream's end and the new stream's start are notified separately.

After receiving a stream notification, the worker checks the current stream state with Twitch before notifying Discord. The first check records the initial state; notifications begin with changes detected by later checks. A stream that starts and ends before the first check is not notified. If Twitch cannot be reached, notifications reflect the state confirmed after a successful retry.

Availability depends on the system operator’s provider configuration. If subscriptions remain pending or notifications fail, check the target name and channel permissions and contact the operator. Users do not enter provider secrets.
