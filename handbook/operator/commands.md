# 運用コマンド一覧

以下はリポジトリルートで実行するWindows／Linux共通のComposeタスクです。Host Pythonは不要です。以下はStageの例です。Prodの起動はsetup.mdの昇格手順を参照してください。

| 用途 | コマンド | 影響・成功確認 |
| --- | --- | --- |
| 設定検査 | `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy check --config-dir data/environments/stage` | 設定とComposeの検査、終了0 |
| Caddy設定生成 | `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy caddy-config --config-dir data/environments/stage --config-dir data/environments/prod --output data/caddy/tueka.caddy` | ドメイン・転送先を記載したサイト設定を生成。[完全な導入手順](caddy.md)でvalidate後に反映 |
| 起動・更新 | `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy up --config-dir data/environments/stage` | Writer停止とMigrationを伴う。Prodは `--stage-config data/environments/stage` 必須。status/healthで確認 |
| 停止 | `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy stop --config-dir data/environments/stage` | DBを含む停止。データVolumeは保持 |
| 状態 | `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy status --config-dir data/environments/stage` | サービス一覧 |
| ログ | `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy logs --config-dir data/environments/stage` | 直近100行。外部共有前に内容確認 |
| health | `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy health --config-dir data/environments/stage` | 観測snapshot。alertsとreadyを確認 |

Backup、Restore、release、abortの正確な引数と前提は `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build recovery --help` と[復旧手順](backup.md)を参照します。復旧先は別Project/Volume、元Writerは停止・隔離を維持します。`release --reconciled` は外部副作用を照合した後だけ使用します。通常のupで復旧保留を迂回しないでください。

定期Jobは `deploy/tueka-backup.service` / `.timer` をHostに合わせて設定します。登録前に停止時間帯、バックアップ先の権限、Host外保管と失敗通知を検証してください。


## 復旧コマンド

以下はProdの復旧例です。先に[復旧手順](backup.md)で別Projectの復元先と対応Image・鍵を準備してください。Backup先before-updateは新しいディレクトリを使用します。

| 用途 | コマンド | 前提・影響・成功確認 |
| --- | --- | --- |
| Backup | `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build recovery backup --config-dir data/environments/prod --bundle data/backups/before-update --resume-source` | Writerを停止して保存し、成功後に元々稼働していたサービスだけ再開。manifest生成とhealth確認 |
| Restore | `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build recovery restore --config-dir data/environments/prod-recovery --bundle data/backups/before-update --source-config data/environments/prod` | 対応Image/鍵、別の空Volume。元Writer停止・起動保留を維持し、検証結果を確認 |
| 解放 | `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build recovery release --config-dir data/environments/prod-recovery --reconciled` | 外部ReceiptとSnapshot以後の副作用を人が照合済みの場合だけ実行。release記録後に通常up |
| 中止 | `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build recovery abort --config-dir data/environments/prod-recovery --source-config data/environments/prod` | 復元先を起動禁止に保ち、元環境のfenceを解除。元の再開は別途up |

Host喪失時のsource-fenced指定は、元Writerが確実に隔離されている証拠を確認した操作者だけが利用します。元Hostの隔離は運用者が実施します。
