# PostgreSQL Migration

現行RuntimeはPostgreSQLを使用します。`migrations/postgresql/0001_initial.sql` が66テーブルとIndex・外部キーを作成し、適用履歴を加えた67テーブルが初期構成です。SQLite用の `migrations/0001_*.sql`〜`0010_*.sql` は過去の履歴であり、新しいCLIでは実行しません。

## 初期化

[導入フロー](setup.md)のstartが、選択したapp.envを使いDB readinessの後でMigrationを実行します。Host側で別のDATABASE_URLを設定して直接実行しません。

Bot・Dashboard・Workerは同じ `DATABASE_URL` を使用します。未適用またはChecksum不一致のSchemaでは起動できません。Repositoryが起動時にテーブルを作成することはありません。

## 更新

1. 対象環境と接続先DBを確認し、Stageで適用・復元を検証します。
2. Bot・Dashboard・Workerを停止します。
3. [論理BackupとTranscript・鍵の保全](backup.md)を実施します。Migration CLIは自動Backupを作りません。
4. [更新手順](upgrade.md)のCLIでMigrationとサービス起動を実行します。

MigrationはDB・Schema単位のTransaction Advisory Lockを取得します。同時実行者は拒否され、未適用SQLと履歴更新は一つのTransactionで処理されます。途中失敗時はDDL・データ・履歴がRollbackされます。再適用は変更を行いません。適用済みファイルの改変、未知の履歴、番号欠落は拒否します。

履歴には番号・ファイル名・LF正規化後のSHA256・UTC epoch秒を記録します。SQL内からのTransaction・Session制御は認めません。通常のDDL/DMLを使い、各文をセミコロンで終えます。条件付き列追加はPostgreSQLの `ADD COLUMN IF NOT EXISTS` を使用します。

## 開発DBの切替

今回の原SQLite DBは破棄可能な開発データです。ETL・Dual Write・旧DBへの逆移送は実装しません。元ファイルを残していてもRuntimeは読み込みません。この例外は将来のStage・本番データには適用しません。

DBの再作成はDiscord上のPanel・Role・Channelを削除しません。空DBではそれらの所有記録も存在しないため、旧PanelからのInteractionで自動復旧・再作成せず、管理者が対象を確認して新しい設定を登録してください。暗号鍵、Transcriptファイル、S3オブジェクトはDBとは別管理です。

## Docker DevのDB

[導入フロー](setup.md)のDev設定を使います。app.envのDATABASE_URLとComposeのPostgreSQLサービスが同じ環境に属することを導入CLIが検証します。ルート.envや.env.postgres-devを新規作成する必要はありません。既存の別ProjectのDBを自動移送・削除することはありません。

## テスト専用PostgreSQL

```sh
docker compose --env-file tests/postgres.env -p tueka-test -f compose.postgres-test.yaml up -d --wait
```

テスト専用URLを `TUEKA_TEST_DATABASE_URL` に設定します。例は `postgresql://tueka_test:tueka_test_local_only@127.0.0.1:55432/tueka_test` です。このServiceはlocalhostのみ公開し、データはtmpfs上にあります。停止・再作成でテストデータは失われます。アプリの開発DBや本番DBには使わないでください。

各テストと型生成はUUID付きSchemaを作り、終了時に削除します。アプリの `DATABASE_URL` はテスト接続先に流用しません。

```sh
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build test-python
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build api-check
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build verify-restore
docker compose --env-file tests/postgres.env -p tueka-test -f compose.postgres-test.yaml down
```

復元検証だけは同じテストServer上にUUID付きDBを3個作成し、実pg_dump/pg_restoreで復元・採番・Queue・失敗時Rollbackを検証して削除します。DB作成権限が必要です。PostgreSQLクライアントがPATHにある場合は `--client-container` を省略できます。
