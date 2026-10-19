---
feature_id: suggestions
title: Suggestions
---

# Suggestions

Members use `/suggest` to open a private form. Submitted answers become an embed in the configured channel. The Bot needs View Channel, Send Messages and Embed Links. Reviewers need a configured review role or Manage Messages.

If the submission form changes while you are answering, run `/suggest` again and re-enter your answers.

In Dashboard → Engagement → Suggestions, select the destination and review roles, define 1–5 form fields (single/multiline, required/optional, maximum length), and configure voting, author visibility and an optional review log. Save to enable. Resources and Bot permissions are rechecked; on a conflict reload before editing again.

A new submission is pending and the author receives its number privately. Click the same vote to cancel, or the opposite vote to change. Approved and rejected suggestions stop accepting votes. Review buttons move an item between pending, in review, approved and rejected. Actor and time are retained; a failed log delivery does not undo review.

Reviewers enter a reason of 1–1000 characters after clicking a review button. Server managers can also review recent suggestions and open their history in the Dashboard. History includes the actor, time and reason. Reload if another reviewer has updated the suggestion. An approved suggestion can be marked Implemented; voting remains closed. The optional review log receives the status and reason, including implementation notices. Without a log destination, the suggestion card and Dashboard still show the result.

Enable “Create a discussion thread” to create a thread attached to each new suggestion. The Bot also needs Create Public Threads, Send Messages in Threads and Read Message History. Open the thread from the suggestion embed or Dashboard after creation. Disabling this option stops new thread creation.

Buttons survive Bot restarts. If submission is queued, keep the suggestion number and wait for publication. For persistent delivery failures, managers check the destination and Bot permissions and give the suggestion number to the operator. Check the channel and delivery state before resubmitting to prevent duplicates. Disabling stops submissions and existing button actions while preserving records.

## Roadmap, labels and duplicate merging

Managers open Suggestion Roadmap to group loaded suggestions by status. Category, tag and status filters run on the server, with 50 records per page and access to older suggestions. Open a suggestion to edit labels, review with a reason, merge duplicates and read history. Other actions and filters pause while a draft is being edited; failed saves preserve input.

Configure up to 20 `categories` and 50 `tags`, each using 1–40 characters without line breaks. Each suggestion accepts one category and up to 10 tags. Removing or renaming an option preserves existing labels; resaving labels requires registered options.

Check the canonical suggestion number and enter a reason before merging. Original posts, votes, discussions and review history remain. Voting closes on the source and its card references the canonical target. Targets must be unmerged suggestions in the same server; an implemented target is supported. Self-merges, expired records and targets with failed publication are rejected. Each canonical target supports up to 100 source suggestions. Changes to either revision require checking again.

Each person counts once. A vote on the canonical target takes precedence; otherwise the newest source vote is used. Cancelling at the target preserves the original votes without reviving an older vote. Merging an existing group into another target retargets its sources and records that history.

## Retention and recovery

New submissions capture `retention_days`, 1–365 days with a default of 30. After expiry the body, votes, history and delivery records are deleted, even when disabled. Physical cleanup resumes on startup if the Bot was stopped. Expired records are hidden from reads. Existing records without expiry keep their lifetime when a retention setting is added.

Answers are included in the database and backups; do not enter secrets. Database expiry does not remove original Discord posts or discussions; managers handle any Discord cleanup separately. Common backup/recovery restores labels, canonical links, original votes and audit history together.
