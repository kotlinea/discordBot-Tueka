---
feature_id: giveaways
---

# Giveaways / Community Events

Enable the feature in the Dashboard and create a giveaway or a first-come community-event registration. Save a draft with a title, description, channel, deadline, capacity and eligibility rules, then choose **Publish to Discord**. The Bot posts Join and Leave buttons. Conditions cannot change after publication; cancel and create a new campaign when needed.

## Entries and closing

Members join or withdraw through the original Bot post and receive a private response. Bots cannot participate. A member needs any required role, while excluded roles take precedence. Minimum account and membership ages are optional. Membership and conditions are checked when joining and again when closing.

Entries and withdrawals stop at the deadline. Community events accept entries in order until capacity is reached and confirm eligible participants at closing. Giveaways select distinct winners from eligible candidates. When fewer candidates remain than requested places, all remaining candidates may win; an empty pool produces no winners. A failed membership lookup aborts that attempt rather than drawing from a partially checked pool.

Managers can close early, cancel or reroll with a reason. Rerolls exclude every previous winner and preserve earlier results, reasons, actors and timestamps. Community-event registrations cannot be rerolled. Public posts show the entry count and winners without mention notifications. Only Guild managers can read the full participant and candidate lists in the Dashboard.

## Failures and disabling

Grant the Bot channel visibility, message history, message sending and embed permissions. An uncertain send is reconciled against the latest 200 messages using the Bot-owned marker. If no receipt is found, processing stops rather than posting a duplicate. Correct permissions or connectivity and retry the failed processing from history. Deleting a known registration post does not automatically create a replacement.

Disabling the feature pauses entries, closing and announcements. Retained records remain readable and work can resume after enabling. Expired data is still purged while disabled. Cancelling preserves history and does not delete the Discord post.

## Limits and retention

Each Guild supports 100 retained campaigns. A campaign supports 1–1,000 places, 1,000 historical participants, 10,000 button interactions, 25 roles per condition list, 1–20 winners and 20 rounds including the initial draw. Deadlines range from 30 seconds to 90 days ahead; retention is 1–365 days. The deadline-based expiry is fixed at publication and rerolls do not extend it. Cancelled campaigns expire after the configured period from cancellation. Expiry deletes internal configuration, entries, results, history and jobs. Discord registration posts and their displayed results are not automatically deleted.
