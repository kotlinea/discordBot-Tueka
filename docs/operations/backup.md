# バックアップと復元

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
5. 必要に応じて[Migration](./migrations.md)を適用します。旧VersionへのRollbackではアプリとDB Snapshotを同じVersionに合わせます。
6. 設定、Social Cursor、Ticket Transcript参照、期限Schedule、Outboxを確認してから各Serviceを起動します。

DBの復元はDiscord上のメッセージ・Role・Channelを巻き戻しません。配送済み副作用は保存済みReceiptと照合し、不明な結果を無条件に再実行しないでください。DB Snapshot後の更新は復元先に含まれません。

空DB・大きなID・採番・Queueと破損dumpのRollbackはテスト環境で検証します。実Transcript/S3と鍵を組み合わせたStage／本番の復旧確認は、別の運用ゲートです。
