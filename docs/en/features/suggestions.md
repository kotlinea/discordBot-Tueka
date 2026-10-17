---
feature_id: suggestions
title: Suggestions
---

# Suggestions

Members use `/suggest` to open a private form. Submitted answers become an embed in the configured channel. The Bot needs View Channel, Send Messages and Embed Links. Reviewers need a configured review role or Manage Messages.

In Dashboard → Engagement → Suggestions, select the destination and review roles, define 1–5 form fields (single/multiline, required/optional, maximum length), and configure voting, author visibility and an optional review log. Save to enable. Resources and Bot permissions are rechecked; on a conflict reload before editing again.

A new submission is pending and the author receives its number privately. Click the same vote to cancel, or the opposite vote to change. Approved and rejected suggestions stop accepting votes. Review buttons move an item between pending, in review, approved and rejected. Actor and time are retained; a failed log delivery does not undo review.

Reviewers enter a reason of 1–1000 characters after clicking a review button. Server managers can also review recent suggestions and open their history in the Dashboard. History includes the actor, time and reason. Reload if another reviewer has updated the suggestion. An approved suggestion can be marked Implemented; voting remains closed. The optional review log receives the status and reason, including implementation notices. Without a log destination, the suggestion card and Dashboard still show the result.

Enable “Create a discussion thread” to create a thread attached to each new suggestion. The Bot also needs Create Public Threads, Send Messages in Threads and Read Message History. Open the thread from the suggestion embed or Dashboard after creation. Disabling this option stops new thread creation.

Buttons survive Bot restarts. If submission is queued, keep the suggestion number and wait for publication. For persistent delivery failures, managers check the destination and Bot permissions and give the suggestion number to the operator. Check the channel and delivery state before resubmitting to prevent duplicates. Disabling stops submissions and existing button actions while preserving records.
