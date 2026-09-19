# 構成と起動

TuekaはBot、Dashboard、Social Workerの3プロセスを同じコードとPostgreSQL DBで動かします。

以下はCompose内で起動するプロセスの一覧であり、Hostで個別に実行する手順ではありません。実際のコマンドは[導入フロー](setup.md)を使います。

| Process | コンテナ内のEntry point | 必須 |
| --- | --- | --- |
| Bot | `python bot.py` | はい |
| Dashboard | `python -m uvicorn dashboard.app:app` | 設定画面を使う場合 |
| Social Worker | `python social_worker.py` | Social通知を使う場合 |

各環境のapp.envから全Processへ同じ`DATABASE_URL`を渡します。PostgreSQLの永続VolumeとTranscriptの保存先・暗号鍵を分けて管理し、外部公開しません。DB readiness、Migration成功、アプリ起動の順に確認します。

## 起動後の確認

- Bot：Discordへ接続し、Application Commandが同期される
- Dashboard：`/docs/`が表示できる。Swagger/OpenAPIは通常404
- Social Worker：DashboardでHeartbeatがonlineになる
- DB：Migration Error、database locked、permission deniedがない

構造化LogへToken、Webhook本文、Ticket本文、外部応答全文を出力しないでください。

Health、Heartbeat、DB/Queueメトリクス、ログとResource制限は[監視と障害対応](monitoring.md)を参照してください。
