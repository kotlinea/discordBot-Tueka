---
feature_id: scheduled_messages
---

# Scheduled Messages / Events

Server managers can schedule Embed announcements and Discord event creation from the Dashboard. Enable the feature in Schedule settings before saving.

## Create a schedule

Choose the kind, title, body and execution time. Times use the device's time zone and are stored as UTC. Schedule at least 30 seconds ahead and within 365 days. Titles allow 100 characters and bodies 2,000 characters.

For a message, choose a server text channel and Embed color. The Bot needs View Channel, Read Message History, Send Messages and Embed Links in that channel. Mentions do not notify users. Repeat once, every 24 hours or every 7 days, up to 365 occurrences with the final time within 365 days. Fixed intervals can display a different local time across daylight-saving changes. Each server may have up to 100 active schedules.

For an event, set its creation time, start, end and external location. Start must be at least 60 seconds after creation; end must be at least 60 seconds after start and within 7 days. The Bot needs Manage Events. Events are created once and do not repeat.

Discord event descriptions allow 1,000 characters including the receipt identifier. Longer bodies end with “…” in the event, while the full body remains saved in the schedule.

## Editing, cancellation and history

Expand delivery and audit history from the list. Editing is available before the first occurrence is reserved. Concurrent updates require reloading; failed saves preserve your draft.

Cancel future delivery cancels unsent work and remaining occurrences. Already posted messages and created events remain. Cancellation is held when a send has started and its result is unknown; check delivery history first.

Reservations finished means all occurrences were reserved or missed. Check delivery history for actual Discord results. Unsent occurrences have a 10-minute grace period, then are skipped. Restarting does not send a burst of overdue announcements.

After an uncertain send, the Bot searches its latest 200 channel messages or the Discord event list for a matching receipt. Missing receipts never cause a blind new send. Reconcile failed delivery retries the same record; an unsent occurrence past its deadline cannot be retried. Deleted or old receipts may require manual investigation.

## Disabling, retention and recovery

Disabling stops new schedules, editing, cancellation and delivery. Overdue occurrences are skipped when re-enabled. A Discord operation that already started may still complete.

Retention is 1–365 days, default 30, captured on creation. Body, audit and delivery records expire that many days after the final scheduled occurrence, or after cancellation. Maintenance deletes expired records even when disabled; when the Bot is stopped it runs after startup. Expired records are hidden from reads.

Bodies are included in the database and backups; do not enter secrets. Use the common backup/recovery process with a consistent database snapshot. Restored sends that had already started resume with receipt reconciliation.
