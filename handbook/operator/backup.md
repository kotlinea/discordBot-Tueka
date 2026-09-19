# バックアップと復元

## Composeの復旧セット

Stage/本番の運用Composeでは次のコマンドで、対応Image・Migration・Queue集計・鍵世代の指紋・PostgreSQL dump・暗号化Transcript/添付を一つのディレクトリへ保存します。既存の保存先を上書きしません。Devは可変Source mountを使うためImageと一致する復旧セットの作成を拒否します。開発DBだけの保全は本ページ後半のDB単体操作を使い、運用復旧は構築済みImageのStageで検証します。

```sh
python scripts/recovery.py backup --config-dir /srv/tueka-config/prod --bundle /srv/tueka-backups/before-update
```

3Serviceを停止して接続が残っていないことを確認し、同じ環境のone-shot `recovery-db`と`recovery-data`を起動します。前者はServerと同じPostgreSQL 18のpg_dump/pg_restore、後者は対象アプリImageの復号/保存処理です。DB・Blob・鍵の検証に失敗した場合はWriterを停止したままにし、自動で再開しません。

通常の定期Backupで成功後に元の稼働Serviceを再開する場合は`--resume-source`を付けます。停止していたServiceを勝手に起動しません。失敗後は原因を確認してから`deploy.py up`を実行してください。

復旧セットの`manifest.json`は最後に作成します。これがないセットは未完成です。`database.dump`と`transcripts.tar`のSHA-256を記録し、復元前に検証します。DBが参照するstatus=readyのTranscript/添付だけを保存し、参照のない一時Blobや削除済みBlobは対象外です。S3参照は実オブジェクトを取得して復号/内容Hashを確認し、同じセットへ暗号文を保存します。S3障害をローカルfallbackで隠してBackup成功とは扱いません。

**暗号鍵・Discord/Provider資格情報はセットに含みません。** `TICKET_ENCRYPTION_KEY`と`SOCIAL_TOKEN_ENCRYPTION_KEY`の同じ世代を秘密管理先へ別途保管してください。セット自体は全体暗号化されておらず、DB dumpには個人情報やOAuth情報を含みます。保存先の閲覧を運用者へ限定し、Host外の保管では暗号化とアクセス制御を適用します。POSIXではディレクトリ0700・データファイル0600、Windowsでは別途ACLを設定します。Checksumは破損検出用で、manifest改変への署名ではありません。

## 別Project／Volumeへの復元

1. `deploy.py init`でSnapshotと**同じ環境**の別設定ディレクトリを用意します。`deployment.json`のProjectは元と異なる`tueka-prod-recovery-...`等、Dashboardポートも未使用のlocalhostポートにします。Imageはmanifestの`image_reference`と`image_id`に一致するものを確保します。別HostではRegistry digestから取得し、Image ID一致を確認します。
2. 対応するDiscord Application設定、暗号鍵世代を秘密管理先から設定します。DB passwordは新しいProject専用の生成値を維持します。`TICKET_S3_BUCKET`は未設定にします。
3. 次を実行します。既存DBや非空Transcript保存先への上書きは拒否します。

```sh
python scripts/recovery.py restore --config-dir /srv/tueka-config/prod-recovery --bundle /srv/tueka-backups/before-update --source-config /srv/tueka-config/prod
```

元のWriterを停止し、元設定へ`recovery-fence.json`、復元先へ`recovery-pending.json`を残します。通常の`deploy.py up`は両方を拒否します。元Hostを失った場合だけ、外部から旧Writerが起動しないことを確認して`--source-config`の代わりに`--source-fenced`を指定します。これは操作者による隔離済みの明示であり、自動で旧Hostを停止する機能ではありません。直接のDocker操作はこの制御を迂回するため使用しないでください。

DBを単一Transactionで復元し、全参照BlobとTicketの回答/Message/Feedback、Social Tokenの暗号文を復号検証します。S3由来のBlobも新Volumeへ復元し、DBのbackendをlocalへ更新します。元S3への書込み/削除はしません。復旧後S3へ戻す場合は別Bucket/Prefixを用意し、通常のpromotion手順で移します。古いHeartbeatは破棄し、Queue/Receipt/Lease/試行回数は保持します。

4. `recovery-pending.json`の検証結果を確認し、Snapshot後のDiscord操作とReceiptを突合します。不明な処理は保留し、Domainの照合・補償手順で解決します。Leaseは期限切れ後に再取得されます。試行回数や配送開始フラグを一括リセットしないでください。
5. 照合後に解放し、対応Imageで起動します。

```sh
python scripts/recovery.py release --config-dir /srv/tueka-config/prod-recovery --reconciled
python scripts/deploy.py up --config-dir /srv/tueka-config/prod-recovery --stage-config /srv/tueka-config/stage
```

`release`は復号とImage/鍵世代を再検査して記録を保存します。外部状態の照合自体は操作者の判断です。実Discordへの送信や自動起動は行いません。元Projectはfenceを保持し、二重Writerの再開を防ぎます。Health確認後の転送先切替とRollbackは[更新手順](upgrade.md)を参照してください。

失敗した復元先は部分データを保持し、通常の起動を禁止します。自動でVolumeを削除したり元環境を再開したりしません。元環境へ戻す場合は`abort`、復元のやり直しは新しい空Projectを使用します。`.recovery.lock`は実行中の排他です。残存時はHost上の実プロセスを確認し、停止済みであることを確認してから運用者が除去します。

## 定期Backup Job

`deploy/tueka-backup.service`と`.timer`はLinux systemd用のテンプレートです。運用アカウント`tueka-operator`、Dockerへのアクセス、仮想環境、設定/Backupディレクトリの所有権を用意し、絶対パスと毎日04:00（HostのTimezone）の停止許容時間帯を調整してから導入します。サービスは`--backup-root`で時刻/UUID付きの保存先を作り、成功時だけ元Serviceを再開します。今回の開発作業ではTimerを登録・有効化していません。

失敗終了を運用通知へ接続し、最終成功時刻、空き容量、別Hostへの転送、定期Restoreを確認します。世代削除は自動化していません。対応するImage/鍵世代を含めて必要な保持期間を決め、復元可能な世代を残してください。

## DB単体の操作

PostgreSQLの論理Backupには、Serverと同じMajor版または互換性を確認済みの新しい `pg_dump` / `pg_restore` を使用します。対象DBの `DATABASE_URL` を設定し、Bot・Dashboard・Workerを停止してから実行します。外部Discord操作の途中状態はDB Snapshotだけでは保護できません。

```sh
python scripts/db_inventory.py --backup data/backups/pre-upgrade.dump
python scripts/db_inventory.py --output data/backups/pre-upgrade-inventory.json
```

Backupはcustom形式です。既存ファイルを上書きせず、失敗時は今回作成した部分ファイルを削除します。CLIは認証情報や行内容を表示しません。Inventoryはテーブル・列・件数を一つのread-only Snapshotから取得します。別時点のBackupとInventoryが一致する必要がある場合は、取得中の書込みを停止してください。

## 保全するもの

- PostgreSQL dumpと対応するアプリVersion・Migration履歴
- 暗号化Transcript、添付ファイル、S3オブジェクトの同じ世代
- `TICKET_ENCRYPTION_KEY`、Social Token暗号鍵など必要な鍵世代
- 環境別の秘密設定と復旧に必要なアクセス情報

鍵やdumpを公開ディレクトリへ置かず、アクセス制限された保存先で管理してください。

## 別DBへの復元

1. 書込み元Serviceを停止し、現DBを保全します。
2. 専用の空PostgreSQL DBを作成し、そのDBを `DATABASE_URL` に設定します。
3. 次のコマンドを実行します。

```sh
python scripts/db_inventory.py --restore data/backups/pre-upgrade.dump
python scripts/db_inventory.py --output data/backups/restored-inventory.json
```

Restoreは空DBだけを許可し、`--single-transaction --exit-on-error` で適用します。失敗時は変更がRollbackされます。接続先の取り違えや書込み競合を防ぐため、復元先へ他Serviceを接続しないでください。

4. 対応するTranscript・S3オブジェクト・暗号鍵を用意し、復号と参照を確認します。
5. 必要に応じて[Migration](migrations.md)を適用します。旧VersionへのRollbackではアプリとDB Snapshotを同じVersionに合わせます。
6. 設定、Social Cursor、Ticket Transcript参照、期限Schedule、Outboxを確認してから各Serviceを起動します。

DBの復元はDiscord上のメッセージ・Role・Channelを巻き戻しません。配送済み副作用は保存済みReceiptと照合し、不明な結果を無条件に再実行しないでください。DB Snapshot後の更新は復元先に含まれません。

空DB・大きなID・採番・Queueと破損dumpのRollbackはテスト環境で検証します。実Transcript/S3と鍵を組み合わせたStage／本番の復旧確認は、別の運用ゲートです。
