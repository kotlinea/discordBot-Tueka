# Getting started

Create a Discord application and Bot, enable Server Members and Message Content intents, and register the exact `DISCORD_REDIRECT_URI` in the Developer Portal.

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
Copy-Item .env.example .env
.venv\Scripts\python.exe migrate.py --database data/tueka.sqlite3 --backup-dir data/backups/migrations
```

Build `dashboard/frontend` and `docs` with `npm ci` and `npm run build`. Start `bot.py`, the Uvicorn dashboard, and `social_worker.py` when social notifications are enabled.

Never expose Uvicorn directly in production. Put it behind an HTTPS reverse proxy.
