---
feature_id: anti_spam
title: Anti-Spam
---

# Anti-Spam

Count activity per user in a time window. Triggers: `message_rate`, `duplicate`, `mention_rate`, `link_rate`, `attachment_rate`, `reaction_rate`, `reaction_burst`. Boundary timestamps count; edits do not increment the counter again.

Combine removal of recent messages with warning points. [Infractions](./infractions) can escalate points to timeout or ban. If several thresholds are crossed together, only the highest applies. Bots and webhooks are excluded by default; use a dedicated actor/channel rule when monitoring integrations.
