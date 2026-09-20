# PostgreSQLのSchema更新

Tuekaの保存先はPostgreSQLです。Schemaの定義と更新SQLは `migrations/postgresql/`、適用履歴はDBの `schema_migrations` に保存されます。

## 導入時

[導入フロー](setup.md)のstartは、対象環境のapp.envにあるDBへ接続し、DB readinessの後にMigrationを実行します。Bot・Dashboard・Social Workerは同じDBを使用します。

アプリの起動には、必要なMigrationがすべて適用済みで、履歴のChecksumがSQLファイルと一致していることが必要です。

## 更新時

1. 対象ImageをStageで受入し、適用と復元の結果を確認します。
2. [Backup手順](backup.md)でDB・Transcript・対応Imageを保全し、同じ世代の暗号鍵を確保します。
3. [更新手順](upgrade.md)で対象Imageを設定し、upを実行します。
4. Migration成功、サービス起動、healthを確認します。

upは稼働中のアプリを停止してからMigrationを実行します。未適用SQLと履歴更新は一つのTransactionで処理され、途中で失敗した場合はRollbackされます。既に適用済みの状態で再実行すると、適用履歴を確認して起動へ進みます。

## 失敗した場合

対象環境のログとMigrationファイルを確認します。適用済みファイルのChecksum不一致、未知の履歴、番号の欠落、同時適用はエラーになります。アプリを停止した状態で原因を解消し、同じupコマンドを再実行してください。

DBとImageを更新前へ戻す場合は、[別Projectへの復元](backup.md)を使用します。Discord上のメッセージやRoleも合わせて照合します。

SQLの追加とテストは[開発者ガイド](../developer/extending.md)、専用DBでの自動検証は[共通タスク](../developer/TOOLS.md)を参照してください。
