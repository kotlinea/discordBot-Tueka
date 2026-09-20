# 構成と起動後の確認

TuekaはBot、Dashboard、Social Workerを環境別Composeで管理し、PostgreSQLへ接続します。起動は[導入フロー](setup.md)、日常操作は[管理コマンド](commands.md)を使用します。

| サービス | 役割 | 起動後の確認 |
| --- | --- | --- |
| Bot | Discordのコマンドとイベント処理 | 専用サーバーで `/ping` と `/help` が応答する |
| Dashboard | サーバー設定、API、利用者Docs | ログイン、サーバー選択、`/docs/`の表示 |
| Social Worker | 外部サービスの更新取得 | Heartbeatと登録アカウントの状態 |
| PostgreSQL | 設定・履歴・配送状態の保存 | Migration成功とhealthのDB状態 |

アプリ設定は環境ごとのapp.envで管理します。DBとTranscriptはそれぞれの永続Volumeへ保存し、暗号鍵と設定をアクセス制限付きの保管先で管理します。

全体の状態は次のコマンドで確認します。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy health --config-dir data/environments/stage
```

Health、ログ、メトリクス、障害時の確認方法は[監視](monitoring.md)を参照してください。
