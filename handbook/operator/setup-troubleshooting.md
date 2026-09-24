# 導入時の問題を調べる

通常の導入手順は[Dockerによる導入](setup.md)を参照してください。

## 設定先が見つからない

`Configuration directory is missing` は、指定した設定先がコンテナから見えない状態です。configure・build・startには同じ `--config-dir` を指定します。Stageの設定を作成した場合は `data/environments/stage`、Devの場合は `data/environments/dev` を使用します。環境名を変えるために設定ファイルをコピーせず、対象環境のconfigureで生成してください。

`Configuration metadata is missing` はsetup.jsonまたはdeployment.jsonが不足しています。configureが成功した設定先を指定してください。

## 排他とDB接続

`configure` は未作成または空の設定ディレクトリへ設定一式を生成し、設定済みの場合は不足項目を補完します。対象パスがファイルの場合、設定一式が不完全な場合、別の操作が排他ロックを保持している場合は、対象パスと確認内容を表示します。

`Operation lock already exists` は、表示された `.recovery.lock` と同じ環境でsetup・deploy・recoveryが実行中、または中断された状態を示します。実行中の処理の終了を確認してください。中断後の環境を継続利用する場合は `recovery-pending.json`・`recovery-fence.json` を確認し、[復旧手順](backup.md)に従います。

Migrationで停止した場合は、表示された `docker logs --tail 100 <project>-migrate-1` で原因を確認します。標準Dev環境の確認コマンド:

```text
docker logs --tail 100 tueka-dev-migrate-1
```

`database_authentication_failed` はDB認証失敗です。対象環境の `app.env` の `DATABASE_URL` と `database-password` を、DB初回起動時の認証情報に揃えます。PostgreSQLの既存Volumeでは、設定ファイルの変更だけでDB内のパスワードは更新されません。元の設定を保管先から復元し、同じstartコマンドを実行してください。元の認証情報が不明な場合はDB管理者による認証情報の復旧が必要です。

`database_dns_failed` はComposeのdatabaseネットワークと接続先名、`database_connection_refused` はPostgreSQLの稼働とポート、`database_connection_timeout` は到達性と負荷、`database_missing` は対象DBとVolumeを確認します。接続先は `postgres:5432`、DB名は環境に対応する `tueka_dev` / `tueka_stage` / `tueka_prod` です。`database_connection_failed` は未分類の接続失敗なので、稼働状態と保存済み設定を照合します。DBのhealthy表示は接続受付の確認であり、アプリ用認証の成功はMigrationで確認します。

調査中はVolumeと設定を保全してください。Migration成功後にBot・Dashboard・Workerが起動します。

### 既存DBのパスワードを現在の設定へ合わせる

`password authentication failed for user "tueka_dev"` があり、現在のDev設定を使って復旧する場合の手順です。DB管理者としてアプリ用Roleのパスワードを変更します。テーブル・データを保持し、マウントされた `database-password` をDB内の認証情報へ適用します。同じRoleを使う他のクライアントも同じ認証情報が必要です。対象Projectが `tueka-dev` であることを確認し、リポジトリルートで実行してください。

PowerShell:

```powershell
Get-Content -Raw deploy/postgres/restore-app-password.sql | docker exec -i -u postgres tueka-dev-postgres-1 psql -X -U postgres -d postgres -v ON_ERROR_STOP=1
```

Linux Shell:

```sh
docker exec -i -u postgres tueka-dev-postgres-1 psql -X -U postgres -d postgres -v ON_ERROR_STOP=1 < deploy/postgres/restore-app-password.sql
```

`ALTER ROLE` が表示されたら再起動します。Roleが存在しない、管理者接続が失敗する場合はそこで停止し、対象Volumeと初期化記録を確認してください。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build setup start --config-dir data/environments/dev
```

ログは `artifacts/<task>/<実行ID>/` です。環境不一致では、表示されたapp.envの `TUEKA_ENV` とsetup.json／deployment.jsonの `environment` を照合します。起動対象を間違えた場合はファイルを書き換えず `--config-dir` を修正してください。必須値の空欄・形式不正も対象ファイル、項目、修正方法に従って直し、同じコマンドを再実行します。

外部設定ディレクトリ、Backup、操作の影響は[運用コマンド](commands.md)と[共通タスク仕様](../developer/TOOLS.md)を参照してください。Registry認証・配布、Caddy配置・systemd操作、定期Backup登録は、それぞれの運用手順に沿って実行します。
