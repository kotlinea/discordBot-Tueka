# 監視と障害時の確認

Bot、Dashboard、Social Workerは5秒ごとにPostgreSQLへHeartbeatと数値メトリクスを保存します。監視の導入前に`0002_observability.sql`までMigrationを適用してください。各Serviceは単一Replicaを前提とします。

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
python scripts/deploy.py health --config-dir /srv/tueka-config/stage
```

対象環境のImageを使う一時コンテナから集計JSONを表示します。`alerts`が空なら終了0、異常やDB取得失敗なら非0です。アプリDBの本文・接続秘密は出力しません。Composeの`status`でコンテナのhealth状態も確認してください。Dockerのunhealthy判定だけではコンテナは自動再起動しません。

`deploy.py init`は環境ごとに`MONITORING_TOKEN`を生成します。既存の`app.env`には32文字以上のランダムな専用Tokenを追加し、Dashboardを再起動します。収集側は保護した資格情報ファイルから`Authorization: Bearer ...`を送信します。TokenをURLやコマンド履歴に記載しないでください。`deploy/nginx.conf`は外部の`/internal/`を404にするため、Host上の収集器はlocalhostのDashboardポートへ直接接続します。

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

Stage実測による運用閾値はまだ確定していません。通常負荷と障害注入の応答時間・Pool待ち・Queue配送時間を記録し、許容遅延を決めてください。収集器の接続失敗、`tueka_database_up == 0`、`tueka_service_ready == 0`、Dead Letter、失効Lease、閾値を超えるQueue遅延を通知対象にします。HTTPエラー率は5分間の5xx増分を全リクエスト増分で割り、トラフィック量と合わせて判断します。

プロセス内Counterは再起動でResetし、Heartbeatを通じた公開は最大約5秒遅れます。欠落・古いHeartbeatのCounterを現在値とみなさず、Service readinessも合わせて確認します。DB停止中はこのDB経由の集計自体も取得できないため、HTTP/probeと収集失敗の監視が必要です。

## ログとResource制限

アプリ標準出力はJSONで、時刻・Service・level・event・コード位置・HTTP status/時間・例外型だけを出します。メッセージ引数、例外本文、リクエストURL/query、Header、Ticket本文、SQL本文は出しません。コード位置と例外型で調査し、秘密値の出力を有効化せずテスト環境で再現します。Uvicornの既定access logはコンテナ入口で無効化します。Host起動も`python -m runtime dashboard`を使用してください。

Composeの各アプリとPostgreSQLはCPU 1、Memory 768 MiB、PID 128、Dockerログ10 MiB×3世代です。Dev ViteはMemory 1 GiBです。これは初期の上限であり、Stageの負荷・OOM・起動時間を測って環境別overrideで調整します。PostgreSQLはSQL/パラメータのログを抑制し、エラーはアプリの分類Counterで確認します。

Host Nginx/TLSは継続使用し、Dashboardはlocalhostに限定します。サンプルaccess logはqueryやIPを保存しません。HostのNginx error logにはリクエスト情報が含まれる場合があるため閲覧を制限し、共有前に確認してください。Host側のlogrotateで`/var/log/nginx/tueka-access.log`を対象に含め、保持期間を運用側で決めます。DockerのローテーションはHost Nginxには適用されません。

## 障害検証と復旧

1. Workerを停止し、`service_unavailable:social-worker`を確認。再起動後にreadyへ戻ることを確認する。
2. 隔離DBで配送失敗と期限超過Queueを作り、Dead Letterと遅延を確認。失敗理由と外部副作用を調べてから再試行する。
3. DBを停止し、livenessは200、readinessは503になることを確認。DB復旧後のHeartbeat・readiness・Queue再開を確認する。
4. Pool枯渇、行lock、deadlockを隔離DBで再現し、待ち時間と分類Counterを確認する。

自動回帰は`tests/test_observability.py`、`tests/test_database.py`と`python scripts/verify_compose.py --image <検証用Image>`です。Compose検証は専用の一時Project/VolumeとオフラインBotを使います。実Discord/OAuth/WebhookによるStage判定は別途必要です。運用DBで障害注入は行わないでください。
