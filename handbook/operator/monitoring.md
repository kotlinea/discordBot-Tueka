# 監視と障害時の確認

Bot、Dashboard、Social Workerは5秒ごとにPostgreSQLへHeartbeatと数値メトリクスを保存します。導入・更新時にMigrationの成功を確認してください。各Serviceは単一Replicaを前提とします。

## Healthとメトリクス

| 入口 | 判定と用途 |
| --- | --- |
| `GET /health/live` | HTTPイベントループの応答。DBや静的資産に依存せず200を返す |
| `GET /health/ready` | DB接続、全MigrationのVersion/Checksum、SPAとDocsのindexを確認。正常200、利用不可503 |
| `GET /internal/metrics` | 専用Bearer Tokenで保護したPrometheus形式。認証不成立404、DB取得失敗503 |
| `python -m observability probe bot` | 同じコンテナのHeartbeatファイル、PID、生存時間、Gateway readinessを確認 |
| `python -m observability probe social-worker` | 同じコンテナのHeartbeatファイルとPIDを確認 |

BotのGateway切断中とHeartbeat保存失敗時はreadyになりません。ファイルの有効期間は30秒です。Dashboard readinessは他のService停止とは独立し、全体の状態はメトリクスまたは次のコマンドで確認します。

```sh
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy health --config-dir data/environments/stage
```

対象環境のImageを使う一時コンテナから集計JSONを表示します。`alerts`が空なら終了0、異常やDB取得失敗なら非0です。出力にはサービス状態、QueueとDBの集計値、アラートが含まれます。Composeの`status`でコンテナのhealth状態も確認してください。unhealthyになった場合はログと依存サービスを調べ、原因の解消後にupで起動を確認します。

新規configureは環境ごとに`MONITORING_TOKEN`を生成します。app.envの値が空欄の場合は、32文字以上のランダムな専用Tokenを設定し、Dashboardを更新します。収集側は保護した資格情報ファイルから`Authorization: Bearer ...`を送信します。TokenをURLやコマンド履歴に記載しないでください。[生成Caddy設定](caddy.md)は外部の`/internal`と`/internal/*`を404にするため、Host上の収集器はlocalhostのDashboardポートへ直接接続します。

## 収集対象と初期閾値

| 指標 | 確認内容 |
| --- | --- |
| `tueka_service_ready` / `tueka_heartbeat_age_seconds` | Service停止・Gateway切断・Heartbeat遅延。欠落時ageは-1、readyは0 |
| `tueka_http_requests_total` | Routeテンプレート・HTTP method・statusクラス別のリクエスト数。5xx率を算出 |
| `tueka_http_request_seconds_sum` / `_count` | 平均応答時間。個別URLやGuild IDは記録しない |
| `tueka_queue_oldest_due_age_seconds` | 実行期限を過ぎた最古の未完了Jobの経過秒。未来のScheduleは除外 |
| `tueka_queue_failed` / `tueka_queue_expired_leases` | Dead Letterと失効Lease。各1件以上で調査 |
| `tueka_job_results_total` / `tueka_provider_errors_total` | Queue確定結果とProvider処理失敗 |
| `tueka_db_pool_waiting_requests` / `tueka_db_pool_wait_seconds_total` | Pool待ち数と累積待ち時間 |
| `tueka_db_pool_request_errors_total` / `tueka_db_pool_connection_errors_total` | Pool取得失敗と接続確立失敗 |
| `tueka_db_errors_total` | deadlock・lock_timeout・query_timeout・connection・other別の失敗 |
| `tueka_postgres_lock_waiters` / `tueka_postgres_oldest_lock_wait_seconds` | 同じアプリRoleのlock待ち数と待っているQueryの経過秒 |
| `tueka_postgres_deadlocks_total` | DB全体のdeadlock累積数。統計Reset時刻も収集 |

初期値はHeartbeat **30秒**、Queue遅延 **300秒**です。`HEARTBEAT_MAX_AGE_SECONDS`（5～3600）と`OUTBOX_MAX_AGE_SECONDS`（1～86400）を`app.env`に設定できます。HTTPとCLIは同じ値を使用し、メトリクスにも閾値を出力します。ローカルprobeの30秒とComposeのprobe間隔は独立した固定値です。

運用閾値はStageでの実測をもとに設定します。通常負荷と障害注入の応答時間・Pool待ち・Queue配送時間を記録し、許容遅延を決めてください。収集器の接続失敗、`tueka_database_up == 0`、`tueka_service_ready == 0`、Dead Letter、失効Lease、閾値を超えるQueue遅延を通知対象にします。HTTPエラー率は5分間の5xx増分を全リクエスト増分で割り、トラフィック量と合わせて判断します。

プロセス内Counterは再起動でResetし、Heartbeatを通じた公開は最大約5秒遅れます。欠落・古いHeartbeatのCounterを現在値とみなさず、Service readinessも合わせて確認します。DB停止中はこのDB経由の集計自体も取得できないため、HTTP/probeと収集失敗の監視が必要です。

## ログとResource制限

アプリログはJSON形式です。時刻・Service・level・event・コード位置・HTTPステータス・所要時間・例外型を確認できます。コード位置と例外型から発生箇所を調べ、テスト環境で再現します。起動とログの確認には[管理コマンド](commands.md)を使用します。

Composeの各アプリとPostgreSQLはCPU 1、Memory 768 MiB、PID 128、Dockerログ10 MiB×3世代です。Dev ViteはMemory 1 GiBです。これは初期の上限であり、Stageの負荷・OOM・起動時間を測って環境別overrideで調整します。PostgreSQLはSQL/パラメータのログを抑制し、エラーはアプリの分類Counterで確認します。

Host Caddyのサービスログはjournalで管理します。アクセスログの既定値は無効です。エラーログにはリクエスト情報が含まれる場合があるため閲覧を制限し、共有前に確認してください。保持期間はHostのjournald運用で定めます。DockerのログローテーションはHost Caddyには適用されません。確認コマンドは[Caddy手順](caddy.md)を参照してください。

## 障害検証と復旧

1. Workerを停止し、`service_unavailable:social-worker`を確認。再起動後にreadyへ戻ることを確認する。
2. 隔離DBで配送失敗と期限超過Queueを作り、Dead Letterと遅延を確認。失敗理由と外部副作用を調べてから再試行する。
3. DBを停止し、livenessは200、readinessは503になることを確認。DB復旧後のHeartbeat・readiness・Queue再開を確認する。
4. Pool枯渇、行lock、deadlockを隔離DBで再現し、待ち時間と分類Counterを確認する。

障害注入は専用の検証環境で行います。Composeによる検証方法は[開発者のテスト手順](../developer/TESTING.md)、実Discord・OAuth・Webhookの確認は[Stage受入](stage-acceptance.md)を参照してください。
