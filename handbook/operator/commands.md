# 運用コマンド一覧

以下の `python` は `.venv-operator` のPythonを使います。Windowsは `.venv-operator/Scripts/python.exe`、Linuxは `.venv-operator/bin/python` です。`CFG` は対象環境の専用設定ディレクトリへ置き換えます。Stageと本番を混同しないでください。

| 用途 | コマンド | 影響・成功確認 |
| --- | --- | --- |
| 設定検査 | `python scripts/deploy.py check --config-dir CFG` | 設定とComposeの検査、終了0 |
| 起動・更新 | `python scripts/deploy.py up --config-dir CFG` | Writer停止とMigrationを伴う。Prodは `--stage-config STAGE` 必須。status/healthで確認 |
| 停止 | `python scripts/deploy.py stop --config-dir CFG` | DBを含む停止。データVolumeは保持 |
| 状態 | `python scripts/deploy.py status --config-dir CFG` | サービス一覧 |
| ログ | `python scripts/deploy.py logs --config-dir CFG` | 直近100行。外部共有前に内容確認 |
| health | `python scripts/deploy.py health --config-dir CFG` | 観測snapshot。alertsとreadyを確認 |

Backup、Restore、release、abortの正確な引数と前提は `python scripts/recovery.py --help` と[復旧手順](backup.md)を参照します。復旧先は別Project/Volume、元Writerは停止・隔離を維持します。`release --reconciled` は外部副作用を照合した後だけ使用します。通常のupで復旧保留を迂回しないでください。

定期Jobは `deploy/tueka-backup.service` / `.timer` をHostに合わせて設定します。登録前に停止時間帯、バックアップ先の権限、Host外保管と失敗通知を検証してください。


## 復旧コマンド

SOURCEは元環境、TARGETは別Projectの空復元先、BUNDLEは新規Backup先／検証済みセットです。

| 用途 | コマンド | 前提・影響・成功確認 |
| --- | --- | --- |
| Backup | `python scripts/recovery.py backup --config-dir SOURCE --bundle BUNDLE --resume-source` | Writerを停止して保存し、成功後に元々稼働していたサービスだけ再開。manifest生成とhealth確認 |
| Restore | `python scripts/recovery.py restore --config-dir TARGET --bundle BUNDLE --source-config SOURCE` | 対応Image/鍵、別の空Volume。元Writer停止・起動保留を維持し、検証結果を確認 |
| 解放 | `python scripts/recovery.py release --config-dir TARGET --reconciled` | 外部ReceiptとSnapshot以後の副作用を人が照合済みの場合だけ実行。release記録後に通常up |
| 中止 | `python scripts/recovery.py abort --config-dir TARGET --source-config SOURCE` | 復元先を起動禁止に保ち、元環境のfenceを解除。元の再開は別途up |

Host喪失時のsource-fenced指定は、元Writerが確実に隔離されている証拠を確認した操作者だけが利用します。これは停止処理の代替自動化ではありません。
