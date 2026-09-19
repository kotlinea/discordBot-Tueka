# 配布用テンプレート

新規導入は[運用者ガイド](../handbook/operator/setup.md)、コマンドは[運用一覧](../handbook/operator/commands.md)を正本とします。以下は既存のHost直接配備用の補助手順です。

# VPS deployment

The shared production image is documented in [container operations](../handbook/operator/container.md). Use the [environment-specific Compose launcher](../handbook/operator/compose.md) for separate dev/stage/prod projects and migration-gated upgrades. The systemd instructions below remain the existing host deployment path.

1. Copy `.env.example` to `.env`, set secrets, and set `DISCORD_REDIRECT_URI` to the public HTTPS callback.
2. In Discord Developer Portal, add that exact URI under OAuth2 Redirects. Enable the **Server Members Intent** and **Message Content Intent** (the dashboard's role/member features and chat filters require them).
3. Create `/opt/discordBot-Tueka/.venv`, install with `python -m pip install --require-hashes -r requirements.lock`, configure PostgreSQL `DATABASE_URL`, and run `/opt/discordBot-Tueka/.venv/bin/python migrate.py` before starting the services.
4. Run `npm ci && npm run build` in both `dashboard/frontend` and `docs`. A release must stop if either build fails.
5. Copy the three systemd files to `/etc/systemd/system/`.
6. Replace `bot.example.com` in `nginx.conf`, install it in Nginx, obtain a Let's Encrypt certificate, and reload Nginx.
7. Run `systemctl daemon-reload && systemctl enable --now tueka-bot tueka-dashboard tueka-social-worker`.

The dashboard is deliberately bound to `127.0.0.1`; only Nginx exposes it over HTTPS.

## Bot permissions

Grant only the features you enable. The dashboard prevents activation when the Bot's guild-role permissions are missing, but channel overwrites can still restrict it.

- Moderation: Manage Messages, Moderate Members, Kick Members, Ban Members. Channel Lock/Lockdown also needs Manage Channels; audit-log actor correlation needs View Audit Log.
- AutoMod / Anti-Spam: Manage Messages for message/reaction removal. Anti-Raid and reaction-rate detection also require the Server Members Intent and reaction events enabled in the Bot.
- Welcome, audit log, tickets, reaction-role panels, polls: View Channel, Send Messages, Embed Links, Read Message History.
- Reaction roles / default role: Manage Roles, with the Bot's role above roles it grants.
- Live statistics / temporary VC / tickets: Manage Channels; temporary VC also needs Move Members.

After deployment, check all services independently with `systemctl status tueka-bot tueka-dashboard tueka-social-worker`, then complete an OAuth login through the public HTTPS URL. The Redirect URI must match the Developer Portal value exactly.

The public documentation is served at `/docs/`. Swagger and OpenAPI are available only with TUEKA_ENV=dev and TUEKA_API_DOCS_ENABLED=true.

## Social notification worker

Set `SOCIAL_WEBHOOK_SECRET` to a random secret and keep `DASHBOARD_BASE_URL` on the public HTTPS origin. YouTube WebSub and Twitch EventSub callbacks are received by the dashboard while provider reconciliation and polling run in `tueka-social-worker`.

`SOCIAL_X_MODE=stream` uses the X filtered stream with timeline polling as gap recovery; use `poll` to disable the persistent stream. TikTok public monitoring requires `yt-dlp` from `requirements.txt`. Instagram public monitoring stays unavailable until `INSTAGRAM_RSS_URL_TEMPLATE` is configured with a fixed operator-controlled URL containing `{account}`. Do not accept feed URLs from dashboard users.
