# 未使用資産の点検

> 履歴資料：記録時点の調査・判断・検証証拠です。現在の作業は[開発者ガイド](../README.md)から開始してください。

点検日: 2026-09-20。起動処理、参照元、テスト、現行計画を照合して削除対象を決定した。実環境のDB、Volume、設定、秘密値は変更しない。

## 削除対象と根拠

| 対象 | 根拠・参照先 |
| --- | --- |
| `banned_words.csv` | 読み取り処理なし。Dockerfileの同梱指定も削除。キーワードはModerationルールから評価する |
| `migrations/0001_*.sql`〜`0010_*.sql`（直下10件） | SQLite用SQL。`database/migrations.py` は `migrations/postgresql/` を使用する |
| `tests/fixtures/moderation_pre_p1.sql` | SQLite移行検証用fixture。現行テストから参照なし |
| `compose.postgres-dev.yaml`、`compose.postgres-test.yaml` | 単独Host開発・テストDBの定義。環境別DBは `deploy/compose.yaml`、テストDBは `compose.tools.yaml` の依存サービスを使用する |
| `tests/postgres.env` | 空の補間ファイル。CIタスクを共通の `deploy/compose.env` に統一 |
| `history/host-services/` の3つのserviceとREADME、`history/nginx.conf` | Host直接アプリ起動とNginx用の実行設定。現在の運用入口はComposeとHost Caddy |
| `moderation/engine.py`、`moderation/models.py` の標準re互換分岐 | `regex` はhash付きLockの必須依存。評価は常にタイムアウト付きで実行する |

## 保持対象

- `migrations/postgresql/`：既存DBのMigration履歴と新規構築に必要。
- `dashboard/api_v1.py`：現行APIの登録入口。ファイル名のv1は削除理由にならない。
- Cog・コマンド別名・Dashboard機能ルート：動的登録と公開コマンド一覧から参照される。
- `moderation/adapter.py`：architecture.mdに将来のDiscordネイティブ同期用契約として明記されている。将来も使用しないと判断できないため保持。
- `deploy/tueka-backup.service` とtimer：現行Backupの定期実行手順で使用する。
- 開発者向け進捗・履歴資料：過去の検証証拠として保持する。当時のファイル名は記録時点のもの。
- テスト内の `.sqlite3` ラベル：`tests/db_support.py` がPostgreSQLの専用Schemaへ対応付ける論理キー。

## 検証

Windows HostのDocker Desktop／Linuxコンテナで以下を実行し、すべて終了コード0を確認した。Remote CI・実Stageの受入とは区別する。

| 共通タスク | 結果 | 証拠（リポジトリ内） |
| --- | --- | --- |
| `ci --group python` | Python 374件、API差分、103コマンドの日英対応、Docsリンク・公開境界、Restore、ツール受入が成功 | `artifacts/ci/20260920T141723-26217aec/` |
| `build-image` | Frontend・日英Docsを含む `tueka:tools` の構築成功 | `artifacts/build-image/20260920T141806-86f1c639/` |
| `verify-runtime --image tueka:tools` | 非root・read-only・SPA/Docs配信、Migration再適用、Worker heartbeat、終了処理、Image内の374テストが成功 | `artifacts/verify-runtime/20260920T142029-7c0c534a/` |

実行形式は `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build <タスクと引数>`。`git diff --check` も成功。
