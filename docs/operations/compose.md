# 環境別Compose

共通定義は`deploy/compose.yaml`、差分は`compose.dev.yaml`・`compose.stage.yaml`・`compose.prod.yaml`。アプリは同じ本番Imageを使い、DevのViteだけNodeを含むdevelopment targetを使う。現在のHost用`compose.postgres-dev.yaml`とは別のProjectであり、既存の開発DBを自動移送・削除しない。

## 環境の作成

Repositoryルートで実行する。Python依存はrequirements.lockから導入しておく。

```sh
docker build -t tueka:local .
python scripts/deploy.py init --environment dev --config-dir data/environments/dev --image tueka:local
```

initは新しいディレクトリだけを作成し、上書きしない。ファイルの役割は次のとおり。

| ファイル | 内容 |
| --- | --- |
| deployment.json | 環境名、Image、Project、Dashboard/ViteのHost port |
| app.env | 環境専用のDiscord/OAuth/Session設定、DATABASE_URL、必要なProvider/暗号鍵設定 |
| database-password | アプリDB Roleのパスワード |
| postgres-admin-password | PostgreSQL管理者の別パスワード |

DB/Session用の乱数は生成するが、Discord資格情報と公開Originは設定者がapp.envへ入力する。Devは専用Botを使い、OAuth callbackの初期値は`http://127.0.0.1:5173/oauth/callback`。Vite portを変えた場合はOrigin/callbackとDiscord Developer Portalも揃える。Stage/本番ではHTTPS OriginとHTTPS Cookieを必須とする。

設定ディレクトリはGit対象外のdata配下または保護された外部ディレクトリに置く。Unixでは親ディレクトリ0700、秘密ファイル0644として、Host上の親ディレクトリでアクセスを制限しつつ、Composeで個別にmountしたファイルを非rootアプリが読めるようにする。Windowsでは設定ディレクトリのACLを運用者に限定する。Composeのfile secretはbind mountであり、Swarmの暗号化Secret保管ではない。DBパスワードは一行で保存し、CRLFを含めない。生成時はOSによらずLF/改行なしとする。

## 起動・停止・更新

```sh
python scripts/deploy.py check --config-dir data/environments/dev
python scripts/deploy.py up --config-dir data/environments/dev
python scripts/deploy.py status --config-dir data/environments/dev
python scripts/deploy.py stop --config-dir data/environments/dev
```

upは設定を検査し、必要なImageを解決してから旧Bot/Dashboard/Workerを停止する。DBのreadinessを待ち、前回のmigrateコンテナを除去して今回のMigrationを実行する。成功後だけ3Serviceを起動する。失敗時は旧Writerを止めたまま終了し、自動的に旧Imageで再開しない。原因を直して同じupを再実行する。更新前BackupとRollback判断は[更新手順](./upgrade)に従う。

単なる`docker compose restart`はImage更新やMigrationを行わないため、リリースには使用しない。Compose定義にもDB healthy→migrate completed successfully→3Serviceの依存を設定するが、稼働中Writer停止と毎回のMigration再実行を保証するのは上記launcherである。

stopはコンテナを停止するだけで、Volumeを消さない。通常運用のlauncherにはVolume削除コマンドを設けない。DB資格情報のファイル変更だけでは既存DB Roleのパスワードは変わらない。初期化SQLは空Volumeでのみ実行されるため、既存DBの資格情報変更は別途Role変更とサービス更新を合わせて実施する。

## Stageから本番へ

Stage/本番のimageには`registry.example/tueka@sha256:...`の完全なdigestを指定する。ローカル検証では`sha256:...`のImage IDも受け付けるが、別Hostへ配布できるRegistry参照ではない。

```sh
python scripts/deploy.py init --environment stage --config-dir data/environments/stage --image REGISTRY_IMAGE_AT_DIGEST
python scripts/deploy.py init --environment prod --config-dir data/environments/prod --image REGISTRY_IMAGE_AT_DIGEST
# それぞれのapp.envへ別のDiscord/OAuth/Session情報と公開Originを設定する
python scripts/deploy.py up --config-dir data/environments/stage
# Stageで実Discord/OAuth/Webhookの受入を完了してから実行する
python scripts/deploy.py up --config-dir data/environments/prod --stage-config data/environments/stage
```

本番upはStage/本番の指定digest一致、別Token/Client ID/Client Secret/Session Secret/callback、Stageの3Serviceが起動中で実際に同じImage IDであることを確認する。これはStageの機能受入を代行しない。両環境が別Docker Hostの場合は、Stageの稼働状態を照合できる運用経路が必要であり、現launcherは同一Docker Hostでの照合を対象とする。遠隔環境への昇格は未実施。

## 分離と永続化

- Projectは`tueka-dev`・`tueka-stage`・`tueka-prod`。Network、Secret mount、VolumeはProjectごとに分かれる。
- PostgreSQLは内部Networkだけに接続し、Host portを公開しない。DB名とアプリRoleは`tueka_ENV`。アプリRoleにsuperuser/createdb/createroleを付けない。
- DBはpostgres-data Volume、Transcriptはtranscripts Volume。BotはTranscriptを書込み、Dashboardは同じVolumeを読取り専用で参照する。Worker/MigrationにはTranscriptをmountしない。
- アプリはUID/GID 10001、read-only root filesystem、cap-drop ALL、no-new-privileges、/tmp tmpfsで動く。各Serviceは当初1 Replica。
- Dashboard公開はlocalhostのみ。既定は本番8000、Stage8001、Dev8002。HostのNginx/TLSを維持し、それぞれの公開Originへ転送する。
- Devだけ必要なソースファイル/ディレクトリを読取り専用bind mountする。Repository全体や.env/dataをmountしない。Uvicorn reloadを有効にし、Viteは5173でSPAを配信し、API/OAuth等をDashboardへ同一Originでproxyする。Bot/WorkerのPython変更はupで再起動する。
- ImageのSPA/Docsは/opt/tueka-assetsへ配置し、Devのソースmountで隠れない。明示したTUEKA_ENV_FILEから秘密値を読み、ソースの.envへのfallbackや`${...}`展開を行わない。

## ローカル受入の再現

`python scripts/verify_compose.py --image tueka:local` はUUID付きの専用Projectを作る。空Volume、非管理者DB Role、同一Image、秘密情報/Network/Volume分離、再起動後のDB/Transcript保持、Schema更新、Migration失敗時のRollback/起動拒否、DevのVite/reloadを確認する。検証Botは実Cogを読み込むがDiscord LoginとCommand同期をMockし、実Guildを変更しない。最後にこの検証で作成したProjectのVolumeだけを削除する。実Stage受入の成功とは区別する。
