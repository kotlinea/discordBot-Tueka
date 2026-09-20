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

ログは `artifacts/<task>/<実行ID>/` です。環境不一致では、表示されたapp.envの `TUEKA_ENV` とsetup.json／deployment.jsonの `environment` を照合します。起動対象を間違えた場合はファイルを書き換えず `--config-dir` を修正してください。必須値の空欄・形式不正も対象ファイル、項目、修正方法に従って直し、同じコマンドを再実行します。

外部設定ディレクトリ、Backup、操作の影響は[運用コマンド](commands.md)と[共通タスク仕様](../developer/TOOLS.md)を参照してください。Registry認証・配布、Caddy配置・systemd操作、定期Backup登録は、それぞれの運用手順に沿って実行します。
