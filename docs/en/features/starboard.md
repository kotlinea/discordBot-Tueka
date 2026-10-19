---
feature_id: starboard
---

# Starboard / Highlights

Highlight posts from explicitly selected channels based on reaction votes. Guild managers enable the feature in the Dashboard and create up to ten boards with source channels, a destination, an emoji and a threshold.

## Sources and votes

Choose 1–25 source channels. Selecting a parent includes its threads; up to 25 channels or threads can be excluded. NSFW posts and Bot posts are excluded. Votes from Bots and the source author do not count. Normal and super reactions count together, once per person.

Thresholds range from 1 to 100 people. Counting is limited to 5,000 users; larger reactions fail rather than publishing a partial count. The Bot needs source viewing/history permissions and destination message/embed permissions.

## Updates and delivery

At the threshold, Tueka posts the first 2,000 characters, author display name, one image and a source link. It follows source edits, vote changes, threshold drops and source deletion. Changing the destination removes only Tueka's recorded highlight before delivery to the new destination.

Deleting the source, its thread or parent channel, or marking the parent NSFW, removes the retained body/image and withdraws the highlight. NSFW source bodies and voters are not fetched.

An uncertain send is reconciled against the latest 200 destination messages. If no receipt is found, delivery fails without a blind resend. Managers can inspect history and retry the same durable record; retry still requires receipt reconciliation.

## Disabling and retention

Turning the whole feature OFF stops fetching and delivery. Records remain readable within retention. Disabling an individual board withdraws its highlights; withdrawal waits while the whole feature is OFF.

New records capture 1–365 retention days, default 30. Settings changes do not extend existing records. Expired content, history and jobs are removed. Retention does not automatically delete Discord source posts or highlight posts. Tracking ends at expiry; manage any remaining Discord highlights directly.

Each board holds up to 1,000 unexpired highlight records. A Guild has up to 1,000 pending source fetches, with a one-day event processing deadline. Repeated pending events for one post are coalesced. Backups include configuration, retained records and receipts.
