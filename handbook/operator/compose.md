# 環境別Compose

Dev、Stage、Prodは環境ごとの設定ディレクトリとCompose Projectで管理します。初回導入は[check・configure・build・start](setup.md)、起動後の操作は[管理コマンド](commands.md)を使用します。

## 設定ファイル

| ファイル | 内容 |
| --- | --- |
| setup.json | ビルド前の環境名・Project・公開ポート |
| deployment.json | 起動に使うImage・環境名・Project・公開ポート |
| app.env | Discord、OAuth、DB、通知Provider、暗号鍵などのアプリ設定 |
| database-password | アプリDB Roleのパスワード |
| postgres-admin-password | PostgreSQL管理者のパスワード |

configureはDBとSessionなどの秘密値を生成します。Discord資格情報と公開URLは運用者がapp.envへ入力します。DevのURLは `http://127.0.0.1:5173`、callbackは `/oauth/callback` です。ポートを変える場合はURLとDiscord Developer PortalのRedirectsも合わせて更新します。

Linuxでは設定ディレクトリ0700、個別の秘密ファイル0644を使用します。Hostでは親ディレクトリでアクセスを制限し、コンテナでは読取り専用で渡したファイルをUID 10001のアプリが参照します。WindowsではディレクトリのACLを運用者に限定します。パスワードファイルは生成された1行の形式を保ちます。

## 起動と停止

以下はStageの例です。Devでは設定ディレクトリを `data/environments/dev` にします。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy check --config-dir data/environments/stage
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy up --config-dir data/environments/stage
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy status --config-dir data/environments/stage
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy health --config-dir data/environments/stage
```

upは設定とImageを確認し、稼働中のBot・Dashboard・Workerを停止します。DB readiness、Migration、サービス起動の順に進みます。Migration失敗時は停止状態を保ちます。ログの原因を解消し、同じupコマンドを再実行してください。

停止する場合:

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy stop --config-dir data/environments/stage
```

stopはDBを含むコンテナを停止し、データVolumeを保持します。更新時は[Backup](backup.md)を取得してからupを使用します。DBパスワードを変更する場合は、DB Roleと設定ファイルを同じ値へ更新する作業が必要です。

## StageからProdへの配布

同じHostでは[導入フローのProd昇格](setup.md#prodへの昇格)を使用します。Prodの起動時にはStageとImageが一致し、Stageの3サービスが稼働していること、環境ごとの資格情報が分離されていることを確認します。機能と公開経路は[Stage受入](stage-acceptance.md)で確認します。

別HostへImageを配布する場合は、Registryの完全なdigest参照（`REGISTRY/IMAGE@sha256:DIGEST`）をdeployment.jsonのimageへ指定します。値は配布担当者から取得してください。新しい設定ディレクトリには、受け取った参照へ `IMAGE_REFERENCE` を置き換えて次を実行します。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy init --environment stage --config-dir data/environments/stage --image IMAGE_REFERENCE
```

生成されたapp.envを編集してからcheck・upへ進みます。initの対象は新しいディレクトリです。Registryへの認証は[共通タスクのRegistry手順](../developer/TOOLS.md#private-registry)を参照してください。Prod昇格の照合対象は同じDocker Host上のStageです。

## ポートと永続化

| 対象 | 配置・既定値 |
| --- | --- |
| Project | tueka-dev / tueka-stage / tueka-prod |
| PostgreSQL | Project専用の内部Network、postgres-data Volume |
| Transcript | transcripts Volume。Botが書込み、Dashboardが読取り |
| アプリ | UID/GID 10001、読取り専用ファイル領域、一時領域は/tmp |
| Dashboard | localhost。Prod 8000、Stage 8001、Dev 8002 |
| Dev Vite | localhost:5173。API・OAuthをDashboardへ転送 |
| Stage／Prodの公開 | Host CaddyでHTTPSへ接続 |

Devではソースを読取り専用で接続し、DashboardのPythonとFrontendを変更すると再読込みします。Bot・Workerの変更はupで反映します。Frontendの依存は専用Volumeへ導入し、upがmount先ディレクトリを準備します。

Backup・Restoreは[recoveryタスク](backup.md)を使用します。復元元のfence、復元先のpending、実行中lockがある環境は起動保留になります。照合と解放は復旧手順に沿って行います。
