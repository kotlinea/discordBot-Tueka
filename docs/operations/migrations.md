# 番号付きDB Migration

明示CLIは、`migrations/0001_名前.sql` から番号順にSQLを適用します。0001はSuggestionsの作成、0002は旧Ticket、0003は旧Reaction Roles、0004は旧Moderation、0005は共有設定FallbackとJSON移行済み判定、0006はSocialの旧単一Template列の削除を扱います。新規導入もこのCLIを先に実行します。0007で現行64テーブル・23Indexと不足列の作成をCLIへ集約しました。RuntimeはDDLを実行せず、DB不存在・未適用・履歴不一致ならSchemaNotReadyで起動を拒否します。

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

0008は7つのOutbox/Scheduleテーブルに取得Token・不足していたLease/試行数/終端日時と検索Indexを追加します。既存Payloadを維持し、完了済み行の終端日時だけを補います。BotとWorkerを停止して適用し、適用後は共通Runnerを使うコードで再起動してください。旧版への復帰は適用前Snapshotを伴う手順で行います。

## Migrationの追加

連続する4桁番号と英小文字・数字・underscoreの名前を使い、各SQL文をセミコロンで終えます。適用済みファイルを編集せず、新しい番号を追加してください。

削除Migrationには次の検証を同じ変更へ含めます。

- 空DB、既存V2、V1/V2混在、直前Version、再適用。
- Snapshot失敗、DDL途中失敗、外部キー検査、Rollback後のデータ保持。
- 削除対象のRuntime読書きとコンストラクタDDLの除去。Bot/Dashboard/Workerの再初期化で旧テーブルが復活しないこと。
- 旧Imageへ戻す手順と、Snapshot復元で失われる更新範囲。

0002は `support_tickets` と `ticket_migrations` を削除し、V2 Ticket・暗号化Transcript・配送待ち処理を保持します。0003は旧 `reaction_role_panels` のみ削除し、V2の付与状態・期限・復旧記録を保持します。

0004は `automod_rules` / `automod_events` / `automod_migrations` / `moderation_migrations` と旧ID列・`guild_users.warn` を削除します。現行のRule・Event・処置結果は子テーブルから退避/再作成し、外部キーの連鎖削除で関連付けが失われないようにします。Case・Point・XP・期限付き処置は保持します。

0005はV2が共有設定から参照していたWelcome・Autorole・Leveling・Auditの実効値を `guild_modules` へ固定し、`guild_settings` を削除します。明示設定、JSONのnull、有効/無効、revisionを保持します。未保存の候補は無効・revision 0で保存し、自動有効化しません。既存Audit設定にカテゴリ指定がない場合だけ、従来有効だったメッセージカテゴリを明示保存します。汎用 `app_metadata` は保持し、JSON移行マーカーだけを削除します。

JSON V1ファイルのImportは廃止しました。起動時にJSONからXP・設定を取り込む処理はありません。旧アプリへのRollbackには適用前Snapshotと対応するファイル・鍵が必要です。Snapshot以後の更新は復元先に含まれません。

0006はSocial購読の旧単一 `template` 列を削除し、現行のイベント別 `templates_json`、購読ID・Target・Cursor・配送履歴を保持します。購読の旧形式を起動時にTargetやイベント別Templateへ変換する処理と、旧 `live` イベントへの配送Fallbackは廃止しました。現在のイベント名は `live_start` / `live_end` です。

共有表内の旧購読行も、残す列の値は変更しません。Targetがない行からTargetを自動作成したり、機能を自動で有効化したりしません。配送には現行Targetが必要です。旧購読の運用を再開する場合は、Dashboardから現行形式で再登録し、重複設定を整理してください。Migrationの更新対象は現行V2のSchemaを持つDBであり、過去の純V1 Schemaへの自動Importは提供しません。適用に失敗した場合は原DBへ手動でDDLを継ぎ足さず、SnapshotとSchemaを確認してください。

## 既存テーブルへの列追加

0007には、以前のRuntimeが行っていた39件の条件付き列追加も含みます。指定列が存在する場合は値と定義を変更せず、不足する場合だけ追加します。Index作成より前に適用します。

```sql
-- tueka: add-column-if-missing
ALTER TABLE example ADD COLUMN new_value INTEGER NOT NULL DEFAULT 0;
```

この注釈はTuekaのCLIが解釈します。単一の `ALTER TABLE ... ADD COLUMN` 以外や、存在しないテーブルへの指定は拒否します。注釈も適用履歴のハッシュ対象です。CLI自身のSchema照会後にSQLの実行制限を適用するため、Migration本文のTransaction / PRAGMA / ATTACH操作は引き続き許可しません。

アプリとMigrationファイルは同じVersionを配布してください。起動エラー時に履歴を手動で書き換えず、3Processを停止して対応するCLIを実行します。SQLの変更が必要なら適用済みファイルを編集せず、次の番号を追加します。
