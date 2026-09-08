# Troubleshooting

- **A saved resource becomes unset:** inspect the 422 field path, guild ownership, required fields, and Bot permissions.
- **409 Conflict:** reload the latest revision and reapply the intended change.
- **Reaction Role does not grant a role:** check Manage Roles, role hierarchy, message access, lock, access policy, binding history, and limits.
- **YouTube RSS returns 404:** verify the channel ID and inspect API or `yt-dlp` fallback and circuit state.
- **Social Worker is offline:** check the process, database path, provider credentials, heartbeat, 429 responses, and next retry time.
- **Ticket transcript fails:** check the encryption key, disk permissions, Discord history permission, S3 settings, and transcript outbox.
