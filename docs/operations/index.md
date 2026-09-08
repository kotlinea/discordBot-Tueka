# 構成と起動

TuekaはBot、Dashboard、Social Workerの3プロセスを同じコードとSQLite DBで動かします。

| Process | Entry point | 必須 |
| --- | --- | --- |
| Bot | `python bot.py` | はい |
| Dashboard | `python -m uvicorn dashboard.app:app` | 設定画面を使う場合 |
| Social Worker | `python social_worker.py` | Social通知を使う場合 |

同じSQLiteを共有するため、全Processで`DATABASE_PATH`を一致させます。SQLiteはWALを使用し、DB、WAL、SHM、Transcript Directoryを同じHostの永続Diskへ置きます。Network Filesystemは使用しません。

## 起動後の確認

- Bot：Discordへ接続し、Application Commandが同期される
- Dashboard：`/api/docs`と`/docs/`が表示できる
- Social Worker：DashboardでHeartbeatがonlineになる
- DB：Migration Error、database locked、permission deniedがない

構造化LogへToken、Webhook本文、Ticket本文、外部応答全文を出力しないでください。
