# Linux / VPSで動かす

## 配置

例として`/opt/discordBot-Tueka`へ配置し、専用Userへ所有させます。`.env`、DB、TranscriptはWeb ServerのDocument Root外へ置きます。

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python migrate_json.py
.venv/bin/python migrate.py --database data/tueka.sqlite3 --backup-dir data/backups/migrations
cd dashboard/frontend && npm ci && npm run build
cd ../../docs && npm ci && npm run build
```

## systemd

`deploy/tueka-bot.service`、`tueka-dashboard.service`、`tueka-social-worker.service`を環境に合わせて配置します。

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tueka-bot tueka-dashboard tueka-social-worker
sudo systemctl status tueka-bot tueka-dashboard tueka-social-worker
```

## NginxとTLS

`deploy/nginx.conf`のDomainと証明書Pathを変更し、全Pathを`127.0.0.1:8000`へProxyします。`X-Forwarded-Proto`と`Host`を渡します。HTTPはHTTPSへRedirectします。

Discord Developer PortalのRedirect URIと`DISCORD_REDIRECT_URI`を公開HTTPS URLへ完全一致させます。
