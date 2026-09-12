# 導入する

## 1. Discord Applicationを作成する

Discord Developer PortalでApplicationとBotを作成し、Bot Tokenを発行します。Tokenは`DISCORD_TOKEN`へ設定し、リポジトリやログへ記録しないでください。

OAuth2 Redirectsへ`DISCORD_REDIRECT_URI`と完全に同じURLを登録します。例は`https://bot.example.com/oauth/callback`です。末尾スラッシュの有無も一致させます。

## 2. Botをサーバーへ追加する

`bot`と`applications.commands`スコープを指定します。権限は利用する機能に合わせて付与してください。Administratorは必須ではありません。

[必要な権限とIntents](./permissions)に、機能別の権限を掲載しています。

## 3. アプリケーションを準備する

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
Copy-Item .env.example .env
.venv\Scripts\python.exe migrate.py --database data/tueka.sqlite3 --backup-dir data/backups/migrations
```

最低限、`DISCORD_TOKEN`、`DISCORD_CLIENT_ID`、`DISCORD_CLIENT_SECRET`、`DISCORD_REDIRECT_URI`、`SESSION_SECRET`を設定します。

## 4. UIとドキュメントをビルドする

```powershell
Set-Location dashboard/frontend
npm ci
npm run build
Set-Location ../../docs
npm ci
npm run build
Set-Location ..
```

## 5. 起動する

```powershell
.venv\Scripts\python.exe bot.py
.venv\Scripts\python.exe -m uvicorn dashboard.app:app --host 127.0.0.1 --port 8000
.venv\Scripts\python.exe social_worker.py
```

Social Workerはソーシャル通知を使用しない場合は省略できます。本番では3プロセスを別サービスとして管理してください。

## 6. 動作を確認する

1. DashboardへDiscordでログインします。
2. 管理するサーバーを選択します。
3. 権限不足の表示がないことを確認します。
4. 必要な機能を設定し、明示的に保存します。
5. Discordで`/ping`と`/help`を実行します。

::: warning HTTPS
公開環境ではDashboardを直接インターネットへ公開せず、NginxなどからHTTPSでリバースプロキシしてください。
:::
