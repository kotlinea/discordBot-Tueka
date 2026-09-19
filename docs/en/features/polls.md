---
feature_id: advanced_polls
title: Advanced polls
---

# Advanced polls

A server manager uses `/poll` to create a button poll with up to ten choices, an optional deadline and image. Separate choices with `|`. The Bot needs View Channel, Send Messages and Embed Links.

After the deadline the result is finalized and buttons stop accepting votes. Deleting the Discord message removes the visible poll; retained data does not recreate that message.
