---
feature_id: tickets
title: Support tickets
---

# Support tickets

Ticket flow: panel message → panel → form → ticket → staff response → close → feedback/transcript. Server managers configure intake; members use a published panel or `/ticket open` (`/t open`).

## Panel editor

Configure six tabs: panel basics (name, channel/private-thread mode, categories, team), button (label/style/emoji/image), welcome embed (title, description, author, images, footer, timestamp, up to 25 fields), permissions (attachments, embeds, emoji/stickers, voice messages), access control (role allow/deny; denial wins), and support hours (IANA timezone, all-day or weekly intervals).

Edits are drafts until saved. Saving checks revision conflicts, Discord resource membership, lengths, URLs and permissions. Reload before reapplying a conflicting draft.

## Member and staff actions

Channel tickets use Claim and staff notes. Private-thread tickets use Join and On-call instead. The opener or authorized staff can close subject to the panel policy; close-request asks staff for approval. Only archived thread tickets can reopen. Staff can manage participants, rename, transfer and use configured canned-response tags according to their permissions.

## Transcript and recovery

Transcripts include answers, message edits/deletions, staff activity, close reason and attachment metadata. Content is encrypted. Access is restricted; do not share private transcript links. Contact the operator if storage is unavailable, giving the ticket ID and time rather than private content.

Before retrying a partially completed action, inspect the ticket and Discord channel. Missing Bot permissions or a deleted category must be corrected by a server manager. Use [all ticket commands](../reference/commands) for arguments and restrictions.
