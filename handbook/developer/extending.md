# 機能を追加する

新しい機能はFeature RegistryへMetadataを登録し、Repository、Service、Discord Cog、API、Dashboard、Docs、Testを同じ変更で追加します。

最初に[設計原則](ENGINEERING.md)と[Backend作業指示](tasks/BACKEND.md)を確認してください。

## Feature Registry

`features/<category>/<id>.py` に `Feature` を定義し、同カテゴリーの `registry.py` へ明示登録します。`id`、category、翻訳Key、Icon、`docs_path`、設定Field、必須Field、必要Bot権限、親機能を定義します。親機能とカテゴリーは別の関係です。日英DocsとUI定義を揃えます。

Bot/APIの入口は `Binding(id, process, "module:callable", order)` で指定します。Botは非同期setup、APIはContextを受け取る同期Router factoryです。共有の実行基盤はカテゴリーBindingへ一度だけ登録します。宣言ファイルからCog・Router・DBをImportせず、DomainからRegistryへ依存させません。

UIは `features/<category>/<id>.feature.tsx` で `defineFeature` の既定画面・経路・Namespace・表示権限を必要な範囲で差し替え、カテゴリーRegistryへ登録します。`.feature.tsx` は既存画面との名前衝突を避ける入口の命名です。設定アクセスは `features/defaults.py` の `SettingsAccess` 契約を使い、汎用Module保存は `ModuleSettingsAccess` を既定とします。revisionを保存先へ渡し、認可・CSRF・TransactionはAdapterとRepositoryで維持します。

設定アクセスを差し替える場合はFeatureの `settings_factory` に `module:callable` を指定し、Contextを受け取って `read / validate / save / additional_permissions` を持つオブジェクトを返します。`dashboard/api/community/welcome.py` が既定保存の実例、`dashboard/api/community/tickets.py` が専用Repository接続の実例です。専用設定APIが書込みを所有する場合は `module_write=False` を宣言します。追加権限は基礎権限へ加算し、認可・Resource検査・revisionを共通境界から外しません。

UIの実例は `features/community/welcome.feature.tsx` と配下の `welcome/Settings.tsx` です。共通 `components/feature/ModuleSettings` に項目描画・見出し・追加操作を渡し、保存と状態表示を再利用します。Buttonは `components/ui/`、EmbedEditorは `components/editors/` を使用します。Embedの制約は生成API型から呼出元で渡します。

単純設定は `community/leveling.feature.tsx` のように `fields` のラベルKey・Resource種別・テンプレート候補を指定します。編集対象の項目一覧はAPI Metadataを使用します。専用保存は `community/tickets.feature.tsx` のように `load` を差し替え、同カテゴリーの専用フォルダーへ画面を置きます。子画面には `nested`、別設定画面には `settingsPath`、Guild外の経路には `standalone` を使います。別設定経路でも専用保存が必要なら `settingsLoad` で画面を指定します。必要な翻訳は `namespaces`、表示名とパンくずは `titleKey / label / breadcrumbs` で指定します。

カテゴリーにはIconと、必要なら `hub` の一覧画面・経路を登録します。Shell、共通Route、Navigation、検索に機能名の分岐を追加しません。`access: 'ticket_staff'` はStaffに見せる入口、`overview: false` は管理者用Overviewを必要としない画面の宣言です。APIの認可を代替しません。ModerationのRule初期値は `defineRuleFeature`、Socialの表示名・注意書き・入力例は `defineProvider` の引数で所有します。

登録テストに加え、`tests/test_welcome_feature.py`、Frontendの `src/test/welcome.test.tsx`、`src/test/routing.test.tsx`、`e2e/features.spec.ts` が保存・直リンク・表示の実例を検証します。全体の段階・受入状態は[専用計画](../../goal.md)を参照してください。

## 登録経路の受入

`tests/test_feature_extension.py` は独立Processでテスト専用機能を既存カテゴリーへ追加し、新カテゴリーの登録・解除も確認します。実Registryの宣言だけをメモリ上で差し替え、通常のSettings、全Bot拡張の起動/終了、API合成、既定設定の保存・revision・CSRFを通します。作業ツリーの起動・合成ファイルは編集しません。

Frontendの `src/test/featureExtension.test.tsx` はRegistryとHTTP応答だけをテスト用に差し替え、実Shellで既定編集・保存、専用画面override、Navigation・検索・パンくず、登録解除後の404を確認します。仮機能は公開Registryや配布機能へ追加しません。

`tests/test_feature_boundaries.py` とFrontendの `src/test/featureBoundaries.test.ts` はDomainからSDK/HTTP、共有基盤から機能、カテゴリー間の内部Importを検査します。相対Import・再Export・文字列による動的Importも対象とし、UIは中間モジュールを辿ります。拒否例のテストも維持してください。これらは通常の `test-python` / `test-web` に含まれます。

## 設定

Guild設定は型、初期値、上限、Discord Resource種別をServer側でも検証します。UIだけに検証を依存させません。複数管理者が編集する設定にはrevisionを付けます。

保存時の既定値・正規化は `guild_settings/<category>/<feature>.py` に置き、同カテゴリーの `registry.py` に `SettingsModel` を登録します。Repositoryへ機能IDの分岐を追加しません。専用の保存Domainを持つ機能は、そのRepositoryを設定Factoryへ渡します。Social Providerは `social/providers/registry.py` へAdapterを明示登録します。

## 非同期処理

保存変更は[番号付きMigration](../operator/migrations.md)へ追加し、RepositoryのコンストラクタへDDLを追加しないでください。接続とTransactionは `database/` を使います。テストDBも先に明示Migrationで作成します。通常のRuntimeテストでは `tests/db_support.py` の `prepare_database` を利用でき、作成したSchemaの後始末をTestCaseのaddCleanupへ登録します。

Discord配送や外部API処理をHTTP Request内で長時間実行せず、OutboxまたはLease付きJobへ保存します。冪等Key、Retry可能／恒久失敗、Timeout、Concurrency上限を定義します。

## ドキュメント

機能Pageには目的、権限、全設定、状態遷移、上限、失敗、復旧、無効化の影響を記載します。実装していない予定機能を現在形で書かないでください。
