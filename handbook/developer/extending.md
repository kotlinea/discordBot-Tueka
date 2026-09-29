# 機能を追加する

新しい機能はFeature RegistryへMetadataを登録し、Repository、Service、Discord Cog、API、Dashboard、Docs、Testを同じ変更で追加します。

最初に[設計原則](ENGINEERING.md)と[Backend作業指示](tasks/BACKEND.md)を確認してください。

## Feature Registry

`features/<category>/<id>.py` に `Feature` を定義し、同カテゴリーの `registry.py` へ明示登録します。`id`、category、翻訳Key、Icon、`docs_path`、設定Field、必須Field、必要Bot権限、親機能を定義します。親機能とカテゴリーは別の関係です。日英DocsとUI定義を揃えます。

新カテゴリーはBackend/UIそれぞれのカテゴリーRegistryを作り、最上位の `features/registry.py` とFrontendの `features/registry.ts` へ一度登録します。Bot専用機能は `dashboard=False` としてUIを省略できます。Help/Ping等のGuild非依存入口は `features/core.py` が所有します。Bot起動・API合成・Shellに機能別分岐を追加しません。

Bot/APIの入口は `Binding(id, process, "module:callable", order)` で指定します。Botは非同期setup、APIはContextを受け取る同期Router factoryです。共有の実行基盤はカテゴリーBindingへ一度だけ登録します。宣言ファイルからCog・Router・DBをImportせず、DomainからRegistryへ依存させません。

UIは `features/<category>/<id>.feature.tsx` で `defineFeature` の既定画面・経路・Namespace・表示権限を必要な範囲で差し替え、カテゴリーRegistryへ登録します。`.feature.tsx` は既存画面との名前衝突を避ける入口の命名です。設定アクセスは `features/defaults.py` の `SettingsAccess` 契約を使い、汎用Module保存は `ModuleSettingsAccess` を既定とします。revisionを保存先へ渡し、認可・CSRF・TransactionはAdapterとRepositoryで維持します。

設定アクセスを差し替える場合はFeatureの `settings_factory` に `module:callable` を指定し、Contextを受け取って `read / validate / save / additional_permissions` を持つオブジェクトを返します。`dashboard/api/community/welcome.py` が既定保存の実例、`dashboard/api/community/tickets.py` が専用Repository接続の実例です。専用設定APIが書込みを所有する場合は `module_write=False` を宣言します。追加権限は基礎権限へ加算し、認可・Resource検査・revisionを共通境界から外しません。

UIの実例は `features/community/welcome.feature.tsx` と配下の `welcome/Settings.tsx` です。共通 `components/feature/ModuleSettings` に項目描画・見出し・追加操作を渡し、保存と状態表示を再利用します。Buttonは `components/ui/`、EmbedEditorは `components/editors/` を使用します。Embedの制約は生成API型から呼出元で渡します。

単純設定は `community/leveling.feature.tsx` のように `fields` のラベルKey・Resource種別・テンプレート候補を指定します。編集対象の項目一覧はAPI Metadataを使用します。専用保存は `community/tickets.feature.tsx` のように `load` を差し替え、同カテゴリーの専用フォルダーへ画面を置きます。子画面には `nested`、別設定画面には `settingsPath`、Guild外の経路には `standalone` を使います。別設定経路でも専用保存が必要なら `settingsLoad` で画面を指定します。必要な翻訳は `namespaces`、表示名とパンくずは `titleKey / label / breadcrumbs` で指定します。

カテゴリーにはIconと、必要なら `hub` の一覧画面・経路を登録します。Shell、共通Route、Navigation、検索に機能名の分岐を追加しません。`access: 'ticket_staff'` はStaffに見せる入口の宣言で、APIの認可を代替しません。ModerationのRule初期値は `defineRuleFeature`、Socialの表示名・注意書き・入力例は `defineProvider` の引数で所有します。

表示カテゴリーは `createRegistry(categories, presentationCategories)` の第2引数で宣言します。項目は `id / titleKey / icon`、順序は配列順です。省略時は既存カテゴリーを表示カテゴリーとして使います。機能の `presentationCategory` は既定で `category` と同じですが、表示だけを移動する場合に差し替えます。Backendのカテゴリー・親・保存先は変えません。Shellは登録順の機能を表示カテゴリー見出しの下へ配置し、`hub` の有無やBackendの親から表示階層を決めません。既存Hubの経路・検索入口は保持します。

`screenKind` は既定が `settings`、複数の操作画面を持つ機能は `workspace` を指定します。Workspaceの `pages` へ `id / path / titleKey / kind / access / load` を登録すると、機能内リンク・Route・パンくずを組み立てます。`path` は機能の主経路からの静的な相対経路、`kind` は通常の移動を表す `navigation` または作成等の画面を開く `action` です。操作入口のクリック自体では保存しません。更新・複製・一括変更の実行とValidationは読み込む機能画面・APIが所有します。動的な詳細経路は `nested` と機能内Routerで扱います。

ページの `access` は明示します。管理者専用機能の子ページをStaffへ開放する登録は拒否します。Staff対応機能の管理者専用ページはリンクを隠し、直URLでもloaderを実行しません。別設定経路は常に管理者専用で、Workspaceの操作リンクを引き継ぎません。ページID・経路重複、不明な表示カテゴリー、機能の親循環もRegistryが拒否し、登録された表示名・項目・ページの翻訳は日英のテストで検査します。

管理者ナビのMetadataは `/guilds/:guildId/features` から独立して取得します。ShellはGuild概要画面でだけOverviewを取得し、Moderation Hub等の固有データは機能画面が取得します。専用画面へ直接入っても機能一覧を表示し、取得失敗を空の一覧として扱いません。Staffは管理者MetadataとOverviewを呼びません。共通Module保存・Suggestions保存後は `['features', guildId]` を無効化して更新値を再取得します。

Guild内の `settings` と最上位の `/servers` 配下はアプリ基盤が所有します。機能・カテゴリー一覧やStandalone経路として重複登録するとRegistryが拒否します。

登録テストに加え、`tests/test_welcome_feature.py`、Frontendの `src/test/welcome.test.tsx`、`src/test/routing.test.tsx`、`e2e/features.spec.ts` が保存・直リンク・表示の実例を検証します。全体の段階・受入状態は[実行計画](EXECUTION_PLAN.md)を参照してください。

## 登録経路の受入

Workspaceの主画面リンク名は `homeTitleKey`（既定は概要）で指定します。内部ページの `group: { id, titleKey }` は同じ目的のページを一つの入口とサブナビへまとめます。Ticketの受付設定はPanels・Panel Messages・Forms・Teams・Tagsをまとめた実例です。グループ内の先頭ページを入口にし、表示権限で除外したページへは誘導しません。グループIDと表示名の不整合は登録時に拒否します。内部ページの `nested: true` は配下の動的詳細を機能内Routerへ委ね、`breadcrumbs` はその詳細のパンくずを宣言します。静的な内部ページを機能内Routerへ重複定義しません。

Ticket/RRは表示カテゴリー `server_operations` に配置します。Ticketの設定別名 `modules/tickets` は `tickets/settings`、RRの `modules/reaction_roles` は `reaction-roles` へ接続します。RRのLink Group・履歴・設定・作成はそれぞれ `link-groups / events / settings / new` です。設定は同じ専用Dialogと保存先を使用します。画面間リンクは機能の絶対経路を使い、RegistryによるRouteの構成変更で戻り先が変わらないようにします。

`e2e/workspaces.spec.ts` は24機能の配置、カテゴリー検索、Ticketの受付設定・詳細・戻り先、RRの内部画面、設定別名、Staffの管理画面拒否、モバイル選択後のフォーカスを検証します。

`tests/test_feature_extension.py` は独立Processでテスト専用機能を既存カテゴリーへ追加し、新カテゴリーの登録・解除も確認します。実Registryの宣言だけをメモリ上で差し替え、通常のSettings、全Bot拡張の起動/終了、API合成、既定設定の保存・revision・CSRFを通します。作業ツリーの起動・合成ファイルは編集しません。

Frontendの `src/test/featureExtension.test.tsx` はRegistryとHTTP応答だけをテスト用に差し替え、実Shellで既定編集・保存、専用画面override、Navigation・検索・パンくず、登録解除後の404を確認します。仮機能は公開Registryや配布機能へ追加しません。

同テストはBackendカテゴリーと異なる表示カテゴリー、Workspaceのページ・操作登録、Metadata失敗、Staffの表示・直URL・loader拒否も通します。`e2e/features.spec.ts` は日英・各画面幅でチケット直アクセス時の24機能ナビとOverview未取得、StaffのMetadata未取得を確認します。

`tests/test_feature_boundaries.py` とFrontendの `src/test/featureBoundaries.test.ts` はDomainからSDK/HTTP、共有基盤から機能、カテゴリー間の内部Importを検査します。相対Import・再Export・文字列による動的Importも対象とし、UIは中間モジュールを辿ります。拒否例のテストも維持してください。これらは通常の `test-python` / `test-web` に含まれます。

## 設定

Moderationの3 Familyは `ruleScreen.tsx` で作成画面のactionを共通登録します。`RuleEditor` と `TriggerFields` を使い、既定値はBackendのtemplate APIから取得します。Trigger項目を追加する場合は、未表示項目を失わない `ruleForm` の変換と新規/複製/再保存のテストを維持してください。一括状態変更は専用APIへID/revision集合を一度だけ送り、逐次PUTへ置き換えないでください。

Guild設定は型、初期値、上限、Discord Resource種別をServer側でも検証します。UIだけに検証を依存させません。複数管理者が編集する設定にはrevisionを付けます。

UIの専用編集画面も共通の未保存・保存中・失敗・破棄・再取得・離脱保護契約に従います。`components/forms/` のdraft/save/guardを使い、保存成功後の応答反映とQuery再取得を機能側で実装してください。設定状態のResource判定はfieldsのresource宣言を利用します。Leveling報酬のように複合値へIDを含む場合は `references: { kind, ids }` で参照IDの抽出を登録し、共有画面へ機能ID分岐を追加しません。稼働結果はDomainの実測APIに基づきます。

保存時の既定値・正規化は `guild_settings/<category>/<feature>.py` に置き、同カテゴリーの `registry.py` に `SettingsModel` を登録します。Repositoryへ機能IDの分岐を追加しません。専用の保存Domainを持つ機能は、そのRepositoryを設定Factoryへ渡します。Social Providerは `social/providers/registry.py` へAdapterを明示登録します。

## 非同期処理

保存変更は[番号付きMigration](../operator/migrations.md)へ追加し、RepositoryのコンストラクタへDDLを追加しないでください。接続とTransactionは `database/` を使います。テストDBも先に明示Migrationで作成します。通常のRuntimeテストでは `tests/db_support.py` の `prepare_database` を利用でき、作成したSchemaの後始末をTestCaseのaddCleanupへ登録します。

Discord配送や外部API処理をHTTP Request内で長時間実行せず、OutboxまたはLease付きJobへ保存します。冪等Key、Retry可能／恒久失敗、Timeout、Concurrency上限を定義します。

## ドキュメント

機能Pageには目的、権限、全設定、状態遷移、上限、失敗、復旧、無効化の影響を記載します。実装していない予定機能を現在形で書かないでください。
