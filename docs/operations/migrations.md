# 番号付きDB Migration

Phase 1で追加した明示CLIは、`migrations/0001_名前.sql` から番号順にSQLを適用します。0001はSuggestionsの3テーブルとIndex、0002は旧Ticketの2テーブル削除を扱います。Bot全体の初期化を置き換えるCLIへの統一は後続作業です。

```sh
python migrate.py --database data/tueka.sqlite3 --backup-dir data/backups/migrations
```

## 実行前

1. まずStageまたはDBの複製へ適用して確認します。
2. 運用DBへ適用する場合はBot・Dashboard・Workerを停止します。SQLiteの書込みロックはDB操作を直列化しますが、外部Discord操作の途中状態までは保護しません。
3. DB、暗号化Transcript、必要な鍵世代を保全します。CLIの自動SnapshotはSQLiteだけが対象です。
4. 空き容量とBackup保存先を確認します。既存DBを開く際はパスの指定間違いがないか確認してください。未存在パスは新規DBとして作成されます。

## 適用と失敗時の動作

- 未適用SQLがあるときだけ、書込みロック取得後・DDL実行前にSQLite Backup APIで新しいSnapshotを作成します。
- Snapshotの整合性・外部キー検証に失敗した場合はMigrationを開始しません。
- 適用履歴は `schema_migrations` に番号・ファイル名・SHA256・適用日時を保存します。SQLの改行コードはLFへ正規化してハッシュ化します。
- 未適用の全ファイルと履歴更新を一つのTransactionで実行します。途中失敗時はDDLとデータ更新をRollbackし、適用前Snapshotを保持します。
- 同じMigrationの再実行は何も変更しません。適用済みファイルの改変、番号欠落、既知ファイルにない適用履歴は拒否します。
- SQL内のCOMMIT / ROLLBACK / SAVEPOINT / PRAGMA / ATTACH / DETACHは拒否します。TransactionやConnectionの制御はCLIが担当します。

異常終了後は、原DBを再開する前に適用履歴・整合性・ログを確認します。DBを自動的にSnapshotで上書きすることはありません。復元する場合は[バックアップと復元](./backup.md)の手順で、停止中に別DBへ復元して検証します。Snapshot以後の変更は復元先に含まれません。

## Migrationの追加

連続する4桁番号と英小文字・数字・underscoreの名前を使い、各SQL文をセミコロンで終えます。適用済みファイルを編集せず、新しい番号を追加してください。

削除Migrationには次の検証を同じ変更へ含めます。

- 空DB、既存V2、V1/V2混在、直前Version、再適用。
- Snapshot失敗、DDL途中失敗、外部キー検査、Rollback後のデータ保持。
- 削除対象のRuntime読書きとコンストラクタDDLの除去。Bot/Dashboard/Workerの再初期化で旧テーブルが復活しないこと。
- 旧Imageへ戻す手順と、Snapshot復元で失われる更新範囲。

0002は `support_tickets` と `ticket_migrations` を削除し、V2 Ticket・暗号化Transcript・配送待ち処理を保持します。0003は旧 `reaction_role_panels` のみ削除し、V2の付与状態・期限・復旧記録を保持します。旧データの自動変換は行いません。旧アプリへのRollbackには適用前Snapshotと対応するファイル・鍵が必要です。Moderationの削除は後続の番号で実施します。
