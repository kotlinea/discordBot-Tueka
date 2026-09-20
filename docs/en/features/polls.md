---
feature_id: advanced_polls
title: Advanced polls
---

# Advanced polls

A member with Manage Server uses `/poll` to post a button poll in the command channel. The question allows up to 256 characters. Separate 2–10 choices with `|`; each choice allows up to 70 characters. Optional duration_minutes sets a deadline of 1–10080 minutes, and image_url accepts an HTTP/HTTPS image. The Bot needs View Channel, Send Messages and Embed Links.

After the deadline the result is finalized and buttons stop accepting votes. Deleting the Discord message removes the visible poll; retained data does not recreate that message.
