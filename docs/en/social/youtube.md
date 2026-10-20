---
feature_id: youtube_updates
---

# YouTube

Register a channel ID, handle or HTTPS youtube.com channel URL. Resolution identifies the canonical channel before notifications become active. Do not rewrite feed URLs to bypass a missing-channel error.

Check preview and choose events/destination. Initial old posts are suppressed. If channel resolution or notifications repeatedly fail, verify the channel still exists and report its URL, time and displayed state to the operator. Provider recovery is handled centrally.

Unicode handles and custom channel URLs are supported. Video uploads and live start/end events are available; live-end handling prefers updating the start notification. Avoid repeatedly deleting/recreating a pending subscription.

Live videos remain monitored after leaving the recent-upload list until their end is confirmed. End notifications remain pending when a video becomes private, is deleted, or its state is otherwise unavailable.
