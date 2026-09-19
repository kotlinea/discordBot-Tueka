---
feature_id: suggestions
title: Suggestions
---

# Suggestions

Members use `/suggest` to open a private form. Submitted answers become an embed in the configured channel. The Bot needs View Channel, Send Messages and Embed Links. Reviewers need a configured review role or Manage Messages.

In Dashboard → Engagement → Suggestions, select the destination and review roles, define 1–5 form fields (single/multiline, required/optional, maximum length), and configure voting, author visibility and an optional review log. Save to enable. Resources and Bot permissions are rechecked; on a conflict reload before editing again.

A new submission is pending and the author receives its number privately. Click the same vote to cancel, or the opposite vote to change. Approved and rejected suggestions stop accepting votes. Review buttons move an item between pending, in review, approved and rejected. Actor and time are retained; a failed log delivery does not undo review.

Buttons survive Bot restarts. Failed initial delivery stays marked as failed: repair channel permissions and ask the member to resubmit. Disabling stops submissions and existing button actions but preserves records.
