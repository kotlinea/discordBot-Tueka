# Dockerによる導入

リポジトリルートから実行します。WindowsはGitとDocker Desktop（Linux containers）、LinuxはGitとDocker Engine／Compose pluginが必要です。Host Python・Node・npm・Playwright・PostgreSQLは不要です。OSへの導入やDockerの起動は管理者が行います。

- Windows: [Docker Desktop導入](https://docs.docker.com/desktop/setup/install/windows-install/)
- Linux: [Docker Engine導入](https://docs.docker.com/engine/install/)、[Compose plugin](https://docs.docker.com/compose/install/linux/)

次のコマンドでリポジトリを取得します。以降もPowerShell／Shell共通で、リポジトリルートから実行します。

```text
git clone https://github.com/kotlinea/discordBot-Tueka.git
cd discordBot-Tueka
```

`--env-file deploy/compose.env` はComposeの補間設定ファイルを指定します。アプリの値は、環境ごとの `app.env` に設定します。

## 1. check

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build check
```

Docker daemon、Linuxコンテナ、Compose、マウント、出力先を確認します。Docker停止時は起動して再実行します。Dockerの起動確認には、PowerShellの `./scripts/setup.ps1` またはShellの `sh scripts/setup.sh` も使えます。設定・ビルド・起動は以下のComposeコマンドで進めます。

## 2. configure

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build setup configure --environment stage --config-dir data/environments/stage
```

`data/environments/stage/app.env` をエディタで開き、Discord Token・Client ID・Client Secret・公開URL・OAuth callbackを設定します。対応するDiscord Applicationの作成・Intentsは[Discord設定](application-setup.md)を参照してください。configureは全項目と説明を生成します。再実行時は入力済みの値・空欄・鍵を保持し、不足項目を補完します。

資格情報は対象のapp.envをエディタで編集して入力します。`setup.json` はビルド前のドラフトです。環境名、公開ポート、対象projectはここで確認します。設定が未入力・不正ならbuildへ進みません。

## 3. build

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build setup build --config-dir data/environments/stage
```

同じDockerfileでアプリ・Frontend・公開Docsを構築し、成功したImage IDを `deployment.json` に固定します。失敗したら設定またはログに示された原因を修正し、同じ段階を再実行します。

## 4. start

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build setup start --config-dir data/environments/stage
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy health --config-dir data/environments/stage
```

DB readiness→Migration→サービス起動→health確認を実行します。Stage／ProdのHTTPS公開は[Host Caddy](caddy.md)に従い別途設定します。再実行時も設定済みの秘密値・鍵・データVolumeを保持します。

## Dev

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build setup configure --environment dev --config-dir data/environments/dev
```

生成されたDevのapp.envを設定してから実行します。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build setup build --config-dir data/environments/dev
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build setup start --config-dir data/environments/dev
```

Devはlocalhost HTTPです。DashboardとViteの公開ポートはdeployment.jsonを確認します。

## Prodへの昇格

実Stage受入を完了した後だけ実行します。Prod用app.envを編集してから、受入済みStageと同じImageを指定します。ProdのbuildはStageのImageを選択し、deployment.jsonへ記録します。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build setup configure --environment prod --config-dir data/environments/prod
```

Prodの資格情報・公開URLを入力・保存した後:

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build setup build --config-dir data/environments/prod --stage-config data/environments/stage
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build setup start --config-dir data/environments/prod --stage-config data/environments/stage
```

## エラーと保存先

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
