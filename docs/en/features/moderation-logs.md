---
feature_id: moderation_logs
title: Moderation logs
---

# Moderation logs

Detection, sanctions and administrator actions share moderation event records. A feature-specific log channel takes precedence over the default moderation destination.

Embeds include event/case identifiers, source, rule, target, channel, reason, actor and action success/failure. Mentions are disabled. View Audit Log permits actor correlation; duplicate records of the Bot's own actions are suppressed.

Evidence retains up to 1,000 message characters and attachment name/type/size. Excluded channels do not retain message bodies; bodies are removed after retention expiry.
