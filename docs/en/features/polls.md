---
feature_id: advanced_polls
title: Advanced polls
---

# Advanced polls

Create and manage polls with role restrictions, multiple choices, disclosure controls and deadlines. The Advanced Polls dashboard provides drafts, editing, copying, moving, closing, reopening, exports and audit/delivery history.

## Create a poll

Server owners, Administrator, Manage Server or a role delegated poll management can create polls.

```text
/poll question:When should we meet? options:Saturday|Sunday|Holiday
/poll-time question:Lunch? options:A|B time:3h
/pollbuilder question:Next event
```

`/poll` and `/poll-time` accept 2–20 options; Builder and Dashboard accept 2–25. Questions allow 1024 characters, descriptions 2000, and each option 256. Maximum choices range from 1 to the smaller of 20 and the option count. More than 20 options use a select menu. Open the options/results browser to read full text across pages.

The optional duration_minutes on `/poll` accepts 1–43200 minutes. Omitting it leaves the poll open until closed manually. image_url accepts one HTTP/HTTPS image. Builder publishes after Create; the Dashboard saves a draft before Publish. Colors and emoji are configurable. Dashboard custom emoji must belong to this server.

The Bot needs View Channel, Send Messages, Embed Links and Read Message History. Thread and pin automation requires the corresponding additional permissions.

## Vote and disclosure

Use buttons for single choices. Multiple-choice and select polls open a private ballot editor; press Confirm to save the complete selection. Confirm an empty selection to withdraw. Empty allowed roles permits everyone; otherwise one matching role is required. Denied roles/users take priority. Bots cannot vote.

| Mode | During voting | After closing |
| --- | --- | --- |
| Anonymous (default) | Public results, hidden individual votes | Same |
| Public | Results, participants and individual votes | Same |
| Secret Winner | Participants only | Results, participants and individual votes |
| Reveal at End | Options only | Results, participants and individual votes |
| Blind | Options only | Results only |
| Custom | Set each item separately | Set each item separately |

Custom independently controls counts/graph, rankings, total votes, participants and individual votes for both stages. Choose everyone, authorized managers or hidden. Individual-vote visibility cannot exceed participant visibility.

Anonymous and Blind hide participants and individual votes even from administrators. User IDs remain in the internal database for duplicate prevention, withdrawal and optional departed-member cleanup. This does not guarantee anonymity from operators with database/backup access. Exports and dashboard responses follow the same disclosure rules.

## Timing, automation and weights

`/poll-schedule` accepts an explicit UTC offset, such as `2027-01-01T12:00:00+09:00`, up to 365 days ahead. Durations support `10m`, `3h` and `1d 3h 15m`, up to 30 days. Relative duration starts when publication is recorded. Maintenance runs every 30 seconds, so publication and display updates may be delayed.

The Dashboard configures participant caps, winner announcements, pinning, discussion threads and ballot removal when members leave or are banned. Automation defaults to off. Hidden results are not announced. Tied winners are announced together.

Role weights range from 1 to 100; the highest matching weight is captured when a ballot is confirmed. Setting changes do not alter existing ballots. Reconfirming evaluates current roles and weights. Participant counts, selections and weighted counts are distinct.

## Manage and export

Use `/poll-list`, `/poll-show`, `/poll-edit`, `/poll-close`, `/poll-reopen`, `/poll-move`, `/poll-copy` and `/poll-delete`. See the [command reference](../reference/commands.md) for arguments.

Once any vote has been cast, question, description, options, eligibility and maximum choices are locked. Color, image, deadline and participant cap remain editable. Editing cannot expand personal-data disclosure. Reopening keeps ballots and cannot undo disclosures that already occurred. Deleting requires confirmation and erases ballots.

Export permitted results with `/poll-export poll_id:1 format:csv` or the Dashboard. Discord attachments are private to the requester. CSV/JSON downloads have an 8 MiB limit, honor disclosure and neutralize spreadsheet formulas in CSV values.

Delegate poll viewing, management, individual-vote viewing, ballot removal, settings and role-weight editing separately. Only server managers can assign these permissions. Weight editing alone cannot grant management rights.

Retention defaults to 90 days after closing, cancellation or deletion and supports 1–365 days. Unpublished drafts expire after 7 days. Uncertain deliveries remain until reconciled. Use Reconcile delivery for failed jobs; messages with unknown receipt state are not blindly posted again. Deleted Discord messages are not recreated automatically.

Disabling polls stops new creation, votes, publication and optional announcements. Reading, exports, manual closure/deletion, deadline processing and disabling voting controls continue. Expired scheduled polls close without publishing; scheduled polls without deadlines publish after re-enabling.
