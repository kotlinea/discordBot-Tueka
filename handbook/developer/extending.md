# 機能を追加する

新しい機能はFeature RegistryへMetadataを登録し、Repository、Service、Discord Cog、API、Dashboard、Docs、Testを同じ変更で追加します。

最初に[設計原則](ENGINEERING.md)と[Backend作業指示](tasks/BACKEND.md)を確認してください。

## Feature Registry

`features/<category>/<id>.py` に `Feature` を定義し、同カテゴリーの `registry.py` へ明示登録します。`id`、category、翻訳Key、Icon、`docs_path`、設定Field、必須Field、必要Bot権限、親機能を定義します。親機能とカテゴリーは別の関係です。日英DocsとUI定義を揃えます。

Bot/APIの入口は `Binding(id, process, "module:callable", order)` で指定します。Botは非同期setup、APIはContextを受け取る同期Router factoryです。共有の実行基盤はカテゴリーBindingへ一度だけ登録します。宣言ファイルからCog・Router・DBをImportせず、DomainからRegistryへ依存させません。

UIは `features/<category>/<id>.feature.tsx` で `defineFeature` の既定画面・経路・Namespace・表示権限を必要な範囲で差し替え、カテゴリーRegistryへ登録します。`.feature.tsx` は既存画面との名前衝突を避ける入口の命名です。設定アクセスは `features/defaults.py` の `SettingsAccess` 契約を使い、汎用Module保存は `ModuleSettingsAccess` を既定とします。revisionを保存先へ渡し、認可・CSRF・TransactionはAdapterとRepositoryで維持します。

設定アクセスを差し替える場合はFeatureの `settings_factory` に `module:callable` を指定し、Contextを受け取って `read / validate / save` を持つオブジェクトを返します。`features/community/welcome.py` と `dashboard/api/community/welcome.py` が実例です。共通Routerへ機能名の条件分岐を追加せず、正規化・組合せ検証をモデルへ置きます。

UIの実例は `features/community/welcome.feature.tsx` と配下の `welcome/Settings.tsx` です。共通 `components/feature/ModuleSettings` に項目描画・見出し・追加操作を渡し、保存と状態表示を再利用します。Buttonは `components/ui/`、EmbedEditorは `components/editors/` を使用します。Embedの制約は生成API型から呼出元で渡します。

welcomeの試験移行を完了しました。他機能とShell全体の移行は[専用計画](../../goal.md)のG3〜G4です。登録テストに加え、`tests/test_welcome_feature.py` とFrontendの `src/test/welcome.test.tsx`、`e2e/welcome.spec.ts` が保存・表示の実例を検証します。

## 設定

Guild設定は型、初期値、上限、Discord Resource種別をServer側でも検証します。UIだけに検証を依存させません。複数管理者が編集する設定にはrevisionを付けます。

## 非同期処理

保存変更は[番号付きMigration](../operator/migrations.md)へ追加し、RepositoryのコンストラクタへDDLを追加しないでください。接続とTransactionは `database/` を使います。テストDBも先に明示Migrationで作成します。通常のRuntimeテストでは `tests/db_support.py` の `prepare_database` を利用でき、作成したSchemaの後始末をTestCaseのaddCleanupへ登録します。

Discord配送や外部API処理をHTTP Request内で長時間実行せず、OutboxまたはLease付きJobへ保存します。冪等Key、Retry可能／恒久失敗、Timeout、Concurrency上限を定義します。

## ドキュメント

機能Pageには目的、権限、全設定、状態遷移、上限、失敗、復旧、無効化の影響を記載します。実装していない予定機能を現在形で書かないでください。
