# 機能を追加する

新しい機能はFeature RegistryへMetadataを登録し、Storage／Repository、Service、Discord Cog、API、Dashboard、Docs、Testを同じ変更で追加します。

## Feature Registry

`id`、category、翻訳Key、Icon、`docs_path`、設定Field、必須Field、必要Bot権限、親Categoryを定義します。`docs_path`に対応する日本語MarkdownはCIで必須です。

## 設定

Guild設定は型、初期値、上限、Discord Resource種別をServer側でも検証します。UIだけに検証を依存させません。複数管理者が編集する設定にはrevisionを付けます。

## 非同期処理

保存変更は[番号付きMigration](../operations/migrations.md)へ追加し、RepositoryのコンストラクタへDDLを追加しないでください。接続とTransactionは `database.py` を使います。テストDBも先に明示Migrationで作成します。通常のRuntimeテストでは `tests/db_support.py` の `prepare_database` を利用でき、旧版Fixtureの試験とは分けます。

Discord配送や外部API処理をHTTP Request内で長時間実行せず、OutboxまたはLease付きJobへ保存します。冪等Key、Retry可能／恒久失敗、Timeout、Concurrency上限を定義します。

## ドキュメント

機能Pageには目的、権限、全設定、状態遷移、上限、失敗、復旧、無効化の影響を記載します。実装していない予定機能を現在形で書かないでください。
