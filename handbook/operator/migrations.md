# PostgreSQL Migration

現行RuntimeはPostgreSQLを使用します。`migrations/postgresql/0001_initial.sql` が66テーブルとIndex・外部キーを作成し、適用履歴を加えた67テーブルが初期構成です。SQLite用の `migrations/0001_*.sql`〜`0010_*.sql` は過去の履歴であり、新しいCLIでは実行しません。

## 初期化

接続先に空のPostgreSQL DBを作り、`DATABASE_URL`を設定します。接続先DBの作成・削除はMigration CLIの責務に含めません。

```sh
python migrate.py
```

Bot・Dashboard・Workerは同じ `DATABASE_URL` を使用します。未適用またはChecksum不一致のSchemaでは起動できません。Repositoryが起動時にテーブルを作成することはありません。

## 更新

1. 対象環境と接続先DBを確認し、Stageで適用・復元を検証します。
2. Bot・Dashboard・Workerを停止します。
3. [論理BackupとTranscript・鍵の保全](backup.md)を実施します。Migration CLIは自動Backupを作りません。
4. `python migrate.py` を実行し、成功後に各Serviceを起動します。

MigrationはDB・Schema単位のTransaction Advisory Lockを取得します。同時実行者は拒否され、未適用SQLと履歴更新は一つのTransactionで処理されます。途中失敗時はDDL・データ・履歴がRollbackされます。再適用は変更を行いません。適用済みファイルの改変、未知の履歴、番号欠落は拒否します。

履歴には番号・ファイル名・LF正規化後のSHA256・UTC epoch秒を記録します。SQL内からのTransaction・Session制御は認めません。通常のDDL/DMLを使い、各文をセミコロンで終えます。条件付き列追加はPostgreSQLの `ADD COLUMN IF NOT EXISTS` を使用します。

## 開発DBの切替

今回の原SQLite DBは破棄可能な開発データです。ETL・Dual Write・旧DBへの逆移送は実装しません。元ファイルを残していてもRuntimeは読み込みません。この例外は将来のStage・本番データには適用しません。

DBの再作成はDiscord上のPanel・Role・Channelを削除しません。空DBではそれらの所有記録も存在しないため、旧PanelからのInteractionで自動復旧・再作成せず、管理者が対象を確認して新しい設定を登録してください。暗号鍵、Transcriptファイル、S3オブジェクトはDBとは別管理です。

## 永続化するローカル開発DB

`.env.postgres-dev`に開発専用の `POSTGRES_DEV_PASSWORD` を設定します。このファイルはGit対象外です。URLへの記載を簡単にするため、十分な長さのランダムな英数字を使用できます。

```sh
docker compose --env-file .env.postgres-dev -p tueka-dev -f compose.postgres-dev.yaml up -d --wait
```

この構成の接続先は `127.0.0.1:55433`、DB名・User名は `tueka_dev`、永続Volumeは `tueka-dev_postgres-dev-data` です。アプリの `.env` で `DATABASE_URL=postgresql://tueka_dev:設定したパスワード@127.0.0.1:55433/tueka_dev` を設定し、`python migrate.py` を実行します。特殊文字を含むパスワードはURLエンコードしてください。変更前のBot・Dashboard・Workerは停止し、空Schemaの作成後に起動します。

破棄可能なローカル開発DBだけを再初期化する場合は、接続先とProject名を確認してから次を実行します。

```sh
docker compose --env-file .env.postgres-dev -p tueka-dev -f compose.postgres-dev.yaml down --volumes
docker compose --env-file .env.postgres-dev -p tueka-dev -f compose.postgres-dev.yaml up -d --wait
python migrate.py
```

この手順は指定した開発ProjectのDB Volumeを削除します。Stage・本番には使用しません。Transcript・暗号鍵・旧SQLiteファイル・Discord ResourceはこのComposeの削除対象ではありません。PostgreSQL初期化後にパスワードを変更しても既存Roleのパスワードは自動変更されません。

## テスト専用PostgreSQL

```sh
docker compose --env-file tests/postgres.env -p tueka-test -f compose.postgres-test.yaml up -d --wait
```

テスト専用URLを `TUEKA_TEST_DATABASE_URL` に設定します。例は `postgresql://tueka_test:tueka_test_local_only@127.0.0.1:55432/tueka_test` です。このServiceはlocalhostのみ公開し、データはtmpfs上にあります。停止・再作成でテストデータは失われます。アプリの開発DBや本番DBには使わないでください。

各テストと型生成はUUID付きSchemaを作り、終了時に削除します。アプリの `DATABASE_URL` はテスト接続先に流用しません。

```sh
python -m unittest discover -s tests -p 'test_*.py'
python scripts/generate_api.py --check
python scripts/verify_postgres_restore.py --client-container tueka-test-postgres-test-1
docker compose --env-file tests/postgres.env -p tueka-test -f compose.postgres-test.yaml down
```

復元検証だけは同じテストServer上にUUID付きDBを3個作成し、実pg_dump/pg_restoreで復元・採番・Queue・失敗時Rollbackを検証して削除します。DB作成権限が必要です。PostgreSQLクライアントがPATHにある場合は `--client-container` を省略できます。
