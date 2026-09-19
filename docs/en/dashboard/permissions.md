# Permission diagnostics

Bot permissions are checked on save and immediately before actions. Inspect server roles, hierarchy and channel/category overwrites.

| Failure | Check |
| --- | --- |
| Message removal | Manage Messages, View Channel |
| Role assignment | Manage Roles, hierarchy |
| Timeout | Moderate Members, hierarchy |
| Channel creation/lock | Manage Channels |
| Private-thread ticket | Manage Threads, Create Private Threads, Send Messages in Threads |
| Unknown log actor | View Audit Log |

Deleted targets and temporary Discord failures are not necessarily permission problems. Inspect event details before changing access.
