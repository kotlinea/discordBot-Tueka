# VPS deployment

1. Copy `.env.example` to `.env`, set secrets, and set `DISCORD_REDIRECT_URI` to the public HTTPS callback.
2. In Discord Developer Portal, add that exact URI under OAuth2 Redirects. Enable the **Server Members Intent** and **Message Content Intent** (the dashboard's role/member features and chat filters require them).
3. Create `/opt/discordBot-Tueka/.venv`, install `requirements.txt`, and run `/opt/discordBot-Tueka/.venv/bin/python migrate_json.py` once before the first start. Then copy the two systemd files to `/etc/systemd/system/`.
4. Replace `bot.example.com` in `nginx.conf`, install it in Nginx, obtain a Let's Encrypt certificate, and reload Nginx.
5. Run `systemctl daemon-reload && systemctl enable --now tueka-bot tueka-dashboard`.

The dashboard is deliberately bound to `127.0.0.1`; only Nginx exposes it over HTTPS.

## Bot permissions

Grant only the features you enable. The dashboard prevents activation when the Bot's guild-role permissions are missing, but channel overwrites can still restrict it.

- Moderation: Manage Messages, Moderate Members, Kick Members, Ban Members.
- Chat filter / anti-spam: Manage Messages.
- Welcome, audit log, tickets, reaction-role panels, polls: View Channel, Send Messages, Embed Links, Read Message History.
- Reaction roles / default role: Manage Roles, with the Bot's role above roles it grants.
- Live statistics / temporary VC / tickets: Manage Channels; temporary VC also needs Move Members.

After deployment, check both services independently with `systemctl status tueka-bot tueka-dashboard`, then complete an OAuth login through the public HTTPS URL. The Redirect URI must match the Developer Portal value exactly.
