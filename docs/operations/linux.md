# Linux / VPSで動かす

## 配置

例として`/opt/discordBot-Tueka`へ配置し、専用Userへ所有させます。`.env`、DB、TranscriptはWeb ServerのDocument Root外へ置きます。

```bash
python3.13 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements.lock
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

## 公開前の実環境確認

- [必要権限とIntents](../guide/permissions.md)をDeveloper PortalとテストGuildで確認します。Token・OAuth Secret・Session Secretは安全に設定し、各SNSのAPI設定・暗号鍵・callbackは[環境変数](../reference/environment.md)と各機能ページに従います。
- 公開HTTPSからOAuthログイン、Guild一覧の認可、権限のないGuildへのアクセス拒否、ログアウト・期限切れセッションを確認します。
- Dashboardで保存・再読込、Botの権限不足表示と不正設定拒否を確認します。利用する各機能はテストGuildで操作から終了・復旧まで確認してください。
- Bot / Dashboard / Workerを個別に再起動し、Command・Webhook・配送・期限処理の再開とログを確認します。TicketはTranscript復号も確認します。
- SQLiteとTranscript・鍵を同じ世代で保全し、[別DBへの復元](./backup.md)を実施します。ローカルの自動テスト成功を、この実環境確認の代替にはしません。
