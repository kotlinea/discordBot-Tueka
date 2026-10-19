---
feature_id: appeals
---

# Appeals / ModMail

Appeal a moderation case or contact server managers privately. Only the author and server managers can read the conversation. Messages are never published in a public channel.

## Member commands

- `/appeal guild_id:SERVER_ID case_id:CASE_NUMBER` appeals your own case. You can use it in the bot's DM after leaving or being removed from the server. Other people's cases are rejected.
- `/modmail guild_id:SERVER_ID` starts a private inquiry. Current membership is checked when you submit.
- Optional `application_id` links your own unexpired application in the same server. It cannot link another person's application.
- `/appeal-status` lists your conversations; provide a conversation number to read messages and replies, including when DM delivery fails.
- `/appeal-reply` replies to an unresolved conversation. `/appeal-withdraw` withdraws it.

Messages contain 1–2000 characters, with a maximum of 100 messages per conversation. Only one unresolved appeal per author/case and one unresolved ModMail per author are allowed. New intake requires a 60-second interval. Never submit passwords, tokens or authentication codes.

## Manager review

Open Appeals / ModMail in the Dashboard and expand a conversation. Save a reply or a reasoned review decision. Replies and decisions reserve DM delivery atomically. Neither the author nor the original moderator can review the appeal; another manager must handle it.

Available states are Reviewing, Accepted, Rejected and Closed. The audit records the reason, reviewer and time. Acceptance records the review decision. Reverse timeouts, bans or other moderation actions separately through Moderation and verify its audit.

Link an existing Ticket belonging to the same author to continue support. Linking does not grant access: Ticket, application and Case screens retain their own authorization and retention rules. Conflicting saves preserve your input; reload current data before retrying.

## DM delivery and retention

Delivery state and failed attempts appear in the conversation. Retry reuses the same delivery record. After an uncertain send, the bot checks its receipts in the latest 200 DMs and does not blindly resend when no receipt is found. The author can read saved replies with `/appeal-status`.

Disabling intake pauses new conversations, replies, review and delivery. Existing data remains readable by its author and managers until expiry. Retention is 1–365 days, default 30, fixed at intake. Expiry cleanup includes disabled servers and resumes after a stopped bot starts. Expired messages and audit cannot be read.

Database backups include messages, replies, audit and delivery receipts. Message bodies are plaintext in the database; operators must restrict database and backup access. Restored uncertain DM deliveries also reconcile receipts.
