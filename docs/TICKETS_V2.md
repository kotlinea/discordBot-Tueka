# Tickets V2 operations

> 最新の正本は[サポートチケット](./features/tickets.md)です。この文書は旧リンクとの互換のため、1リリースだけ保持します。

Tickets V2 is released together with Dashboard V2. Enable it only after the
Bot, dashboard, and rebuilt frontend assets have been deployed from the same
revision.

## Required environment

- `TICKETS_V2=true` enables the workflow. `TICKETS_V2_GUILDS` may contain a
  comma-separated guild allowlist during rollout.
- `TICKET_ENCRYPTION_KEY` is required before intake can be enabled. Generate a
  Fernet key once, store it in the service secret store, and keep it available
  for as long as retained transcripts exist. Do not rotate it by replacement.
- `DASHBOARD_BASE_URL` is required for OAuth-protected transcript links in DMs.
- The `TICKET_S3_*` variables are optional. When configured, an upload is
  verified before S3 becomes authoritative. Encrypted local blobs remain the
  fallback and are retried by the Bot maintenance loop.

Example key generation:

```powershell
.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Discord permissions

The Bot needs Manage Channels, Manage Threads, Create Private Threads, Send
Messages in Threads, Read Message History, Manage Messages, Send Messages,
Embed Links, and Attach Files. Role hierarchy still applies to every action.

## Storage and retention

Ticket messages, form answers, staff notes, transcripts, and retained
attachments are encrypted with the configured key. Attachments are limited to
25 MiB each and 100 MiB per Ticket. Transcript retention defaults to 365 days
and accepts 1–3650 days. The hourly maintenance pass deletes expired blobs and
message/form bodies while preserving non-content statistics.

SQLite must be on local storage and shared by the Bot and dashboard. WAL is
enabled. Back up the database, encrypted blob directory, encryption key, and S3
bucket as one recovery set.

## Rollout and rollback

1. Install updated Python dependencies and build `dashboard/frontend`.
2. Set `DASHBOARD_UI_V2=true`, `TICKETS_V2=true`, the encryption key, and an
   optional guild allowlist.
3. Restart dashboard and Bot. Migration is transactional and idempotent.
4. Verify the Ticket overview, create a Channel and Thread test Ticket, close
   both, and open the OAuth transcript URL.
5. To roll back execution, set `TICKETS_V2=false` and restart both processes.
   Legacy settings and commands remain available for the compatibility release.

Legacy plaintext transcripts are encrypted and verified before their SQLite
plaintext field is cleared. Never remove the old columns manually during the
compatibility release.
