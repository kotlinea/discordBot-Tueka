# Social Workerの運用

## 起動

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy up --config-dir data/environments/stage
```

Bot、Dashboard、Workerは環境別Composeで管理します。上記はWriter停止とMigrationを伴う起動・更新です。設定とhealthの確認は[運用コマンド](commands.md)を参照してください。

## リースと復旧

Workerは`social_targets`をリース取得します。二重起動しても同じ対象を同時監視せず、期限切れリースは再取得されます。起動時に未確認対象、Webhook購読、Stream Rule、CursorをDBから復旧します。

共有`httpx.AsyncClient`、Provider別Semaphore、Timeout、429のRetry-After、指数BackoffとJitterを使用します。

## 状態

| 状態 | 意味 | 対応 |
| --- | --- | --- |
| 確認待ち | 初期解決前 | Worker起動と資格情報を確認 |
| 稼働中 | 最終確認成功 | 対応不要 |
| degraded | Fallback動作または一時障害 | Provider詳細と次回実行を見る |
| unavailable | 必要設定不足 | 環境変数を設定して再起動 |
| failed | 継続不能 | Errorと対象IDを修正して再確認 |

Heartbeat、最終成功、遅延件数、Provider Error、Delivery失敗をDashboardと構造化Logで確認します。外部応答全文、Webhook本文、Tokenはログへ残しません。
