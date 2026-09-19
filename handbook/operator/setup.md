# クローンから起動まで

## 前提を準備する

Windows: Git、Python 3.13（py launcher）、Docker Desktopを導入し、Linux containersを選択します。Linux: Git、Python 3.13とvenv、Docker EngineとCompose pluginを導入し、実行アカウントでDockerを操作できることを確認します。OSへの導入はこのスクリプトでは行いません。管理者権限の付与はHost管理者が判断してください。

不足時のOS別手順は[Windows](windows.md)・[Linux](linux.md)を参照してください。

```text
git clone https://github.com/kotlinea/discordBot-Tueka.git
cd discordBot-Tueka
```

以下のコマンドはすべて、クローンしたリポジトリのルート（`scripts` ディレクトリがある場所）から実行します。WindowsはPowerShell、LinuxはShellの例を使用してください。`check`・`configure`・`build`・`start` は単独のコマンドではなく、導入スクリプトに渡す引数です。

## 設定の正本

DockerのDev／Stage／Prodのアプリ設定は、各設定ディレクトリの `app.env` に統一します。ルート `.env` の作成・編集・コピーは不要で、起動時にも読み込みません。既存 `.env` の必要な値を移す場合はローカルエディタで対象環境を確認し、app.envの該当項目だけへ転記してください。生成されたDB接続先・秘密値を旧設定で上書きしないでください。

`setup.json`／`deployment.json` はImage・Project・Hostポートの管理情報、`database-password`／`postgres-admin-password` はPostgreSQL用の生成ファイルです。別のアプリ設定元ではありません。既存DBのパスワード変更はapp.envだけの書換えでは行えません。

## 1. check

Windows（リポジトリのルートから）:

```powershell
./scripts/setup.ps1 check --config-dir data/environments/stage
```

Linux:

```sh
bash scripts/setup.sh check --config-dir data/environments/stage
```

Pythonの実行ファイルを明示する場合は、環境変数 `TUEKA_SETUP_PYTHON` にPython 3.13の絶対パスを設定します。

設定作成後にcheckを再実行すると、設定されたHostポートの競合も検査します。既に起動済みの同一Projectは競合扱いしません。

両方とも専用 `.venv-operator` にhash付きLockの依存を準備します。ホスト側のNode/npmは不要です。

## 2. configure

Windows:

```powershell
./scripts/setup.ps1 configure --environment stage --config-dir data/environments/stage
```

Linux:

```sh
bash scripts/setup.sh configure --environment stage --config-dir data/environments/stage
```

`setup.json` は起動できないドラフトです。ここで一度止まり、生成された `data/environments/stage/app.env` をローカルエディタで編集・保存してからbuildへ進みます。専用Discord Bot Token、Client ID/Secret、公開HTTPS originと完全一致するOAuth callbackを設定してください。[Application手順](application-setup.md)を参照します。Ticketを使う場合の暗号鍵・Socialの資格情報は[環境変数](environment.md)を確認してください。

生成されたDB用秘密値、Session/Monitoringの値は環境ごとに別です。既存ディレクトリの再configureは秘密値・鍵を再生成しません。設定はGitへ追加しないでください。Linuxでは親ディレクトリ0700、Windowsでは運用者だけが参照できるACLをHost側で設定します。コンテナへ渡すfile secretの読取りはUID 10001に必要です。

## 3. build

Windows:

```powershell
./scripts/setup.ps1 build --config-dir data/environments/stage
```

Linux:

```sh
bash scripts/setup.sh build --config-dir data/environments/stage
```

未入力・不正設定ならDocker build前に停止します。成功したImage IDを `deployment.json` へ固定します。ビルド失敗時はドラフトを保ち、修正後に同じコマンドで再開できます。完成済み設定への再buildは既存Imageを確認するだけで再構築しません。更新は[更新手順](upgrade.md)を使います。

## 4. start

Windows:

```powershell
./scripts/setup.ps1 start --config-dir data/environments/stage
```

Linux:

```sh
bash scripts/setup.sh start --config-dir data/environments/stage
```

初回はHostポートも確認し、PostgreSQL readiness→Migration→Bot/Dashboard/Worker→healthの順で確認します。失敗した場合にVolumeやDBを消してやり直さないでください。設定・ログを修正して該当段階から再開します。公開前にNginx/TLS、OAuth callback、通知先を[Stage受入](stage-acceptance.md)で確認します。実Discordへ接続するため、専用検証Bot/Guildを用意してください。

## Devで導入する場合

Stageとは別の設定ディレクトリを使用します。Dashboard8002/Vite5173、Stage8001、本番8000が既定です。変更はドラフトまたはdeploymentのport値で行います。DevのVite依存は専用Volumeへ入り、Host側には空mountpointだけが必要です。

Windows:

```powershell
./scripts/setup.ps1 check --config-dir data/environments/dev
./scripts/setup.ps1 configure --environment dev --config-dir data/environments/dev
```

Linux:

```sh
bash scripts/setup.sh check --config-dir data/environments/dev
bash scripts/setup.sh configure --environment dev --config-dir data/environments/dev
```

`data/environments/dev/app.env` を編集・保存した後、次を実行します。

Windows:

```powershell
./scripts/setup.ps1 build --config-dir data/environments/dev
```

build成功後:

```powershell
./scripts/setup.ps1 start --config-dir data/environments/dev
```

Linux:

```sh
bash scripts/setup.sh build --config-dir data/environments/dev
```

build成功後:

```sh
bash scripts/setup.sh start --config-dir data/environments/dev
```

## 本番へ昇格する場合

担当者がStage受入を完了したことを記録してから実行してください。本番用にImageを再ビルドしません。以下は同一HostにStage設定と受入済みImageがある場合の手順です。別HostではRegistryの同一digestをpullし、両環境のimage参照を同一のdigestに固定する既存[Compose手順](compose.md)を使います。

Windows:

```powershell
./scripts/setup.ps1 check --config-dir data/environments/prod
./scripts/setup.ps1 configure --environment prod --config-dir data/environments/prod
```

Linux:

```sh
bash scripts/setup.sh check --config-dir data/environments/prod
bash scripts/setup.sh configure --environment prod --config-dir data/environments/prod
```

`data/environments/prod/app.env` に本番用の資格情報・公開URLを設定し、保存します。その後、受入済みStageのImageを固定します。

Windows:

```powershell
./scripts/setup.ps1 build --config-dir data/environments/prod --stage-config data/environments/stage
```

上記が成功した後:

```powershell
./scripts/setup.ps1 start --config-dir data/environments/prod --stage-config data/environments/stage
```

Linux:

```sh
bash scripts/setup.sh build --config-dir data/environments/prod --stage-config data/environments/stage
```

上記が成功した後:

```sh
bash scripts/setup.sh start --config-dir data/environments/prod --stage-config data/environments/stage
```

Nginx/TLS、Registry認証・push、Backup timer、通知先設定は自動変更しません。既存DB・Volume・鍵の削除やデータ移送も行いません。
