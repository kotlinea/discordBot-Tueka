---
feature_id: x_updates
---

# X

Register an account ID or handle and select a notification channel. The provider’s collection mode is controlled by the operator, not by individual server users.

The initial check suppresses historical posts. Polling retrieves available pages after the last successful check and queues posts from oldest to newest. If acquisition fails partway through, the next attempt starts from the previous checkpoint. Posts beyond the provider’s accessible history or service limits cannot be guaranteed.

Availability and timeliness depend on the provider service. Inspect pending/failed state, confirm the public target and channel permissions, and report persistent failures to the operator.
