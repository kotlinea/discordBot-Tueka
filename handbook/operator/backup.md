# バックアップと復元

## Composeの復旧セット

Stage/本番の運用Composeでは次のコマンドで、対応Image・Migration・Queue集計・鍵世代の指紋・PostgreSQL dump・暗号化Transcript/添付を一つのディレクトリへ保存します。保存先には新しいディレクトリを指定します。対象環境は、構築済みImageで稼働するStage／Prodです。

```sh
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build recovery backup --config-dir data/environments/prod --bundle data/backups/before-update
```

3Serviceを停止して接続が残っていないことを確認し、同じ環境のone-shot `recovery-db`と`recovery-data`を起動します。前者はServerと同じPostgreSQL 18のpg_dump/pg_restore、後者は対象アプリImageの復号/保存処理です。DB・Blob・鍵の検証に失敗した場合は、アプリを停止した状態で原因を確認します。

通常の定期Backupで成功後に元の稼働Serviceを再開する場合は`--resume-source`を付けます。再開対象はBackup前に稼働していたServiceです。失敗後は原因を確認し、[管理コマンド](commands.md)のupで再開します。

復旧セットの`manifest.json`は最後に作成します。これがないセットは未完成です。`database.dump`と`transcripts.tar`のSHA-256を記録し、復元前に検証します。DBが参照するstatus=readyのTranscript/添付だけを保存し、参照のない一時Blobや削除済みBlobは対象外です。S3参照は実オブジェクトを取得して復号/内容Hashを確認し、同じセットへ暗号文を保存します。S3の取得・検証に失敗した場合はBackup失敗となります。

**暗号鍵・Discord/Provider資格情報は、復旧セットとは別の秘密管理先で保管します。** `TICKET_ENCRYPTION_KEY`と`SOCIAL_TOKEN_ENCRYPTION_KEY`の同じ世代を秘密管理先へ別途保管してください。セット自体は全体暗号化されておらず、DB dumpには個人情報やOAuth情報を含みます。保存先の閲覧を運用者へ限定し、Host外の保管では暗号化とアクセス制御を適用します。POSIXではディレクトリ0700・データファイル0600、Windowsでは別途ACLを設定します。Checksumは破損検出用で、manifest改変への署名ではありません。

## 別Project／Volumeへの復元

Prod復元先の設定生成例です。initの後に、下の手順でdeployment.jsonとapp.envを編集します。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy init --environment prod --config-dir data/environments/prod-recovery --image IMAGE_REFERENCE
```

1. 上記のinitコマンドでSnapshotと**同じ環境**の別設定ディレクトリを用意します。`IMAGE_REFERENCE`はmanifestの参照へ置き換えてください。`deployment.json`のProjectは元と異なる`tueka-prod-recovery-...`等、Dashboardポートも未使用のlocalhostポートにします。Imageはmanifestの`image_reference`と`image_id`に一致するものを確保します。別HostではRegistry digestから取得し、Image ID一致を確認します。
2. 対応するDiscord Application設定、暗号鍵世代を秘密管理先から設定します。DB passwordは新しいProject専用の生成値を維持します。`TICKET_S3_BUCKET`は未設定にします。
3. 次のrestoreコマンドを実行します。復元先は空のDB・Transcript Volumeを持つ別Projectです。

```sh
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build recovery restore --config-dir data/environments/prod-recovery --bundle data/backups/before-update --source-config data/environments/prod
```

restoreは元のアプリを停止し、元設定へ`recovery-fence.json`、復元先へ`recovery-pending.json`を保存します。どちらも起動保留の状態になります。元Hostを失った場合は、運用者が電源・Network等で元Hostを隔離してから、`--source-config`の代わりに`--source-fenced`を指定します。起動保留の解除には本ページのrelease・abortを使用します。

DBを単一Transactionで復元し、全参照BlobとTicketの回答/Message/Feedback、Social Tokenの暗号文を復号検証します。S3由来のBlobも新Volumeへ復元し、DBのbackendをlocalへ更新します。復元元のS3オブジェクトは保全されます。S3を再利用する場合は別Bucket/Prefixを用意してapp.envへ設定します。Botの定期処理がLocalの対象をアップロードし、整合性を確認します。古いHeartbeatは破棄し、Queue/Receipt/Lease/試行回数は保持します。

4. `recovery-pending.json`の検証結果を確認し、Snapshot後のDiscord操作とReceiptを突合します。不明な処理は保留し、Domainの照合・補償手順で解決します。Leaseは期限切れ後に再取得されます。試行回数や配送開始フラグを一括リセットしないでください。
5. 照合後に解放し、対応Imageで起動します。

```sh
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build recovery release --config-dir data/environments/prod-recovery --reconciled
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build deploy up --config-dir data/environments/prod-recovery --stage-config data/environments/stage
```

`release`は復号とImage/鍵世代を再検査して記録を保存します。外部状態の照合自体は操作者の判断です。起動はreleaseの後にupコマンドで行います。元Projectはfenceを保持し、二重Writerの再開を防ぎます。Health確認後の転送先切替とRollbackは[更新手順](upgrade.md)を参照してください。

失敗した復元先は部分データを保持し、通常の起動を禁止します。調査と再試行のため、両環境のVolumeと停止状態を保持します。元環境へ戻す場合は`abort`、復元のやり直しは新しい空Projectを使用します。`.recovery.lock`は実行中の排他です。残存時はHost上の実プロセスを確認し、停止済みであることを確認してから運用者が除去します。

## 定期Backup Job

`deploy/tueka-backup.service`と`.timer`はLinux systemd用のテンプレートです。運用アカウント`tueka-operator`、Dockerへのアクセス、Docker／Compose、設定/Backupディレクトリの所有権を用意し、絶対パスと毎日04:00（HostのTimezone）の停止許容時間帯を調整してから導入します。サービスは`--backup-root`で時刻/UUID付きの保存先を作り、成功時だけ元Serviceを再開します。登録後はTimerの次回実行時刻と手動実行の結果を確認します。

失敗終了を運用通知へ接続し、最終成功時刻、空き容量、別Hostへの転送、定期Restoreを確認します。運用者が保持期間を決め、対応するImage・鍵とセットで世代を管理します。削除前に必要な世代を復元できることを確認してください。

## DB単体の操作

Backup／Restoreは `recovery` タスクで実行します。PostgreSQL clientはタスクのコンテナ内に用意されます。DB単体の復元検証は[開発者のテスト手順](../developer/TESTING.md)を参照してください。

## 保全するもの

- PostgreSQL dumpと対応するアプリVersion・Migration履歴
- 暗号化Transcript、添付ファイル、S3オブジェクトの同じ世代
- `TICKET_ENCRYPTION_KEY`、Social Token暗号鍵など必要な鍵世代
- 環境別の秘密設定と復旧に必要なアクセス情報

鍵やdumpを公開ディレクトリへ置かず、アクセス制限された保存先で管理してください。

## 別DBへの復元

上記の別Projectへの `recovery restore` を使用します。元Writerを停止し、鍵・Image・Transcriptを同じ世代に揃えてください。Discord上の副作用は巻き戻らないため、Receiptを照合してから `release --reconciled` を実行します。実S3を含む復旧は実Stage受入で確認します。
