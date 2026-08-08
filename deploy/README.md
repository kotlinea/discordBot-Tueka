# VPS deployment

1. Copy `.env.example` to `.env`, set secrets, and set `DISCORD_REDIRECT_URI` to the public HTTPS callback.
2. In Discord Developer Portal, add that exact URI under OAuth2 Redirects and configure the Bot's privileged intents.
3. Create `/opt/discordBot-Tueka/.venv`, install `requirements.txt`, and run `/opt/discordBot-Tueka/.venv/bin/python migrate_json.py` once before the first start. Then copy the two systemd files to `/etc/systemd/system/`.
4. Replace `bot.example.com` in `nginx.conf`, install it in Nginx, obtain a Let's Encrypt certificate, and reload Nginx.
5. Run `systemctl daemon-reload && systemctl enable --now tueka-bot tueka-dashboard`.

The dashboard is deliberately bound to `127.0.0.1`; only Nginx exposes it over HTTPS.
