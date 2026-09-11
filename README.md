# Tueka

Tuekaは、Discordサーバーのモデレーション、コミュニティ運営、チケット対応、リアクションロール、ソーシャル通知を一つのダッシュボードから管理するBotです。

## 構成

```text
管理者 ──HTTPS──> Dashboard ──┐
                              ├──> SQLite (WAL)
外部SNS ──Webhook/Poll──> Social Worker ──┤
                              └──> Discord Bot ──> Discord
```

- **Discord Bot**：Discordイベントの受信、コマンド、Role・Channel操作、通知配送
- **Dashboard**：Discord OAuth、設定、検証、Webhook受付、公開ドキュメント
- **Social Worker**：YouTube、Twitch、X、TikTok、Instagramの監視とイベント正規化
- **SQLite**：設定、ルール、ケース、Ticket、Social Event、Outboxを共有

## 最短セットアップ

1. Python 3.13で仮想環境を作成し、`pip install --require-hashes -r requirements.lock`を実行します。
2. `.env.example`を`.env`へコピーし、Discord BotとOAuthの値を設定します。
3. `python migrate_json.py`でDBを初期化し、`python migrate.py --database data/tueka.sqlite3 --backup-dir data/backups/migrations`で番号付きMigrationを適用します。DBパスを変更している場合は引数も合わせます。既存環境は先に全Processを停止・Backupしてください。
4. Botを`python bot.py`、Dashboardを`python -m uvicorn dashboard.app:app --host 127.0.0.1 --port 8000`で起動します。
5. ソーシャル通知を使う場合は`python social_worker.py`も起動します。

管理画面はReact SPAです。起動前に`dashboard/frontend`で`npm ci`と`npm run build`を実行します。ビルド済み資産がない場合は503を返します。

ドキュメントサイトは`docs`で`npm ci`と`npm run build`を実行すると、Dashboardの`/docs/`から公開されます。

## テスト

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
cd dashboard/frontend
npm test
npm run build
cd ../../docs
npm run build
```

導入、必要権限、全機能、運用、障害対応は[公式ドキュメント](docs/index.md)を参照してください。公開環境では`/docs/`、APIのSwagger UIは`/api/docs`です。V2完全移行、リファクタリング、Docker化、機能開発の実施順序は[開発ロードマップ](ROADMAP.md)を正本とします。

## セキュリティ

`.env`、SQLite DB、Transcript、バックアップを公開ディレクトリへ置かないでください。Discord Token、OAuth Secret、暗号鍵、SNS API Keyは環境変数だけで管理し、漏えい時は直ちに再発行します。
