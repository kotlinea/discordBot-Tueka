# アーキテクチャ

## 境界

Dashboardの共通入口は概要とサーバー情報です。サーバー情報はGuild一覧とDiscord Resourceの取得値を表示し、機能設定は各機能画面が所有します。サーバー運営（Ticket/RR）・コミュニティ・エンゲージメント・モデレーション・通知とソーシャルの表示所属はUI Registryへ集約します。Sidebar・検索・パンくずが同じ登録を使用し、Backendの機能ID・カテゴリー・保存先は表示移動と独立しています。

| 表示カテゴリー | 機能ID（24公開機能） |
| --- | --- |
| サーバー運営 | `tickets`、`reaction_roles` |
| コミュニティ | `welcome`、`autorole`、`leveling`、`live_stats`、`temporary_voice` |
| エンゲージメント | `advanced_polls`、`suggestions`、`minigames` |
| モデレーション | `moderation`、`automod`、`anti_spam`、`anti_raid`、`infractions`、`moderation_actions`、`moderation_logs`、`audit_log`、`trust_score` |
| 通知・ソーシャル | `youtube_updates`、`twitch_updates`、`tiktok_updates`、`x_updates`、`instagram_updates` |

カテゴリーは探索の見出し、機能は目的別の入口です。Ticket/RRのような大機能は内部に複数画面を持ち、各画面を機能専用フォルダーへ置きます。機能別ファイルは登録入口の単位であり、実装全体を一ファイルへ集約する規則ではありません。共通入口は機能数に含めず、Bot専用機能に架空のDashboard画面を作りません。

- **Repository**：PostgreSQLへの読書き、Transaction、Lease、Revision
- **Service**：検証、状態遷移、冪等性、権限に依存しない業務処理
- **Discord Adapter / Cog**：Discord Event、Interaction、Permission、API操作
- **Dashboard API**：OAuth、CSRF、Guild所属、Payload Validation
- **Worker**：外部Provider、Cursor、Webhook購読、Polling

## 共通パターン

`features/<category>/<feature>.py` が機能MetadataとProcess別Bindingを宣言し、各カテゴリーの `registry.py` と最上位Registryで明示登録します。宣言のImportはSDK・HTTP・DBを読み込みません。`features/loading.py` は起動対象Processの参照だけを解決します。カテゴリーは表示・登録単位で、DomainのTransaction所有境界は維持します。

Botは登録された拡張を一度だけ初期化し、登録失敗時は読み込んだ拡張を解除します。APIはアプリごとにContextを生成し、各Router factoryへ同じContextを一度ずつ渡します。重複Binding、親の循環、API経路・operation IDの衝突を拒否します。

Session・Guild選択・healthはアプリ基盤として機能登録から独立させます。UIのGuild内 `settings` と最上位 `/servers` 配下は基盤の予約経路です。機能の既存URLと優先順位を保持し、機能経路・カテゴリー一覧・Standaloneから基盤への衝突も登録時に拒否します。

Frontendは `features/<category>/<id>.feature.tsx` に経路、画面loader、Namespace、表示権限、設定項目の表示、パンくずを定義します。RegistryはID・親・経路を検査し、同じloaderの並行呼出しをまとめます。Backend Metadataと生成API型を使い、認可はAPI境界で確認します。`routing/RegisteredFeatures.tsx` がGuild内の画面を、`StandaloneFeatures.tsx` がTranscript等を読み込み、Guild・機能経路単位で編集状態を分離します。カテゴリーRegistryは一覧画面とナビゲーションのIconも所有し、Shellは機能IDの分岐を持ちません。

汎用設定は `features/DefaultSettings.tsx` が登録された項目表示を共通Formへ渡します。機能定義の `fields` はラベル・Resource種別・テンプレート候補の表示指定であり、保存対象や必須条件はAPI Metadataを使います。ルール画面は `settingsPath` で別の設定経路を登録します。カテゴリー内の `defineRuleFeature` と `defineProvider` は実在する共通画面を組み立て、初期Trigger・Provider名等を機能別に受け取ります。

表示カテゴリーはRegistryの `presentationCategories`、機能側の所属は `presentationCategory` が所有します。Backendカテゴリー・親とは独立し、カテゴリー見出しと機能リンクを同じ階層で組み立てます。既定の `screenKind: settings` を `workspace` に差し替え、静的な内部画面を `pages` に登録すると、Route・内部ナビ・操作入口・パンくずへ接続します。動的詳細画面は機能内Routerが所有します。`action` は画面を開く入口であり、共有ナビにDomainの更新処理を持ち込みません。

Shellの管理者Metadata取得は `/guilds/:guildId/features` を使用し、各画面のOverview取得と分離します。Guild確認後だけ取得し、Staffでは管理者向けのどちらも取得しません。登録された管理者専用内部画面は直URLでもloader実行前に拒否します。これは表示側の保護であり、APIのGuild認可・CSRF・revision検査は独立して維持します。

`welcome` の入力は `cogs/community/welcome.py`、設定モデルは `guild_settings/community/welcome.py`、API設定Factoryは `dashboard/api/community/welcome.py` が担当します。参加ロールは独立した `cogs/community/autorole.py` が担当します。Featureの `settings_factory` はアプリのContextへ `SettingsAccess` を一度生成し、共通Routerが認可・CSRF・Resource確認後に検証と保存を呼びます。既定の `ModuleSettingsAccess` は正規化とrevision付き保存を提供します。

DashboardのSession・Discord OAuth state・ユーザー個人設定は `dashboard/repository.py` が保存します。Web画面とJSON APIはこのRepositoryを直接使用します。

TicketのTeam所属判定は `ticketing/access.py` が所有し、SessionのGuild一覧とTicket APIが同じ関数を利用します。共通SessionからTicket Router内部へ依存させません。Guild所属が失われた利用者には、明示Team割当が残っていても権限を与えません。

依存境界はPython/TypeScriptの構文木で検査します。Domainのモデル・Repository・ServiceはSDK/HTTPと実行Registryに依存せず、外部Adapterを明示分離します。共有UIから機能への逆依存と、カテゴリー間の内部Importを拒否します。権限の表示は `components/PermissionDiagnostics.tsx` に文言を渡し、機能画面から全体のNavigation合成へ依存させません。登録追加・解除の統合検査は[拡張手順](extending.md)を参照してください。

Guild Moduleの汎用CRUD・有効Guild一覧は `guild_settings/repository.py`、既定値・正規化は `guild_settings/<category>/<feature>.py` が担当します。Domain内の `guild_settings/registry.py` で明示登録し、実行機能のRegistryには依存しません。APIとCogは設定アクセス契約・設定Repositoryと各DomainのRepositoryを使用します。

| ディレクトリ | 責務 |
| --- | --- |
| `dashboard/` | Session、Discord OAuth state、個人設定、公開HTTPの入口 |
| `dashboard/api/` | Domain別Router、共通Dependency、Resource検証、API応答 |
| `guild_settings/` | Moduleの有効化、設定の正規化、保存・revision |
| `community/` | 一時VC、テキストXP・音声XP、ランキングの保存 |
| `engagement/` | Pollと投票、期限切れの保存処理 |
| `social/` | Repository、モデル、Token暗号化、Provider、Webhook検証、Worker実装 |
| `moderation/` | Repository、ルール検証・評価、Discord入力変換、処置Service。Case、Trust、証拠、Lockdown、期限処理もこのDomainに含む |
| `ticketing/` | Ticketのモデル、Repository、Service、暗号化Transcript |
| `reaction_roles/` / `suggestions/` | 各機能のモデル、Repository、Service |
| `cogs/` | Discordに登録する各Domainの入口。設定とDomain保存を明示的に利用 |

Moderationのルール更新と設定のrules_revision更新、CaseとTrustイベントの記録は同じTransactionを維持するため `moderation/repository.py` がまとめて扱います。一般的な設定保存をこの経路へ集約しません。TicketのBlacklist・当番・Tag・Panel移動・自動Close除外・削除記録もRepositoryが扱い、ServiceやCogから直接SQLを実行しません。

`social_worker.py` は登録されたWorker Bindingを事前検証し、TaskGroupで一度ずつ起動します。処理本体は `social/worker.py`、Provider別取得は `social/providers/<provider>.py`、構築は同フォルダーの `registry.py` が担当します。APIの内部生成関数はPostgreSQL接続URLを受け取り、DomainごとのRepositoryを生成します。HTTP URLと認可の契約は維持します。共通Outbox/Runnerは `jobs/` にあります。Discord操作はDomainのAdapterへ分離済みです。API Routerは `dashboard/api/<category>/` に配置し、`dashboard/api_v1.py` はContextの生成とRouterの合成だけを担当します。

Runtime・Migration・テスト基盤はPostgreSQLを使用します。

`database/connections.py` がpsycopg接続・有界Pool・Transaction、`database/migrations.py` が適用と履歴検査、`database/operations.py` が棚卸し・論理Backup/Restoreを担当します。Poolは接続先ごとに最大4接続、取得待ち10秒、SQL30秒、lock待ち10秒です。UTC epoch秒を保存し、JSONはTEXT、既存の真偽値は0/1、Discord IDはBIGINT、内部IDはIdentity列を使います。

Schemaは番号付きMigration CLIだけが作成・変更します。RepositoryのコンストラクタはDDLを実行せず、未適用・不一致の履歴を検出すると `SchemaNotReady` で失敗します。BotはDiscord接続前、Dashboard / Workerは保存層の作成時に確認します。現行Ticketの未完了Close復旧やReaction Rolesの不足設定修復は、Schema変更とは別のDomain処理として保持しています。

認証後の管理画面はReact SPAを常時配信します。公開ランディングと404画面のみJinjaを使用します。Frontendをbuildしていない場合、管理画面は503を返します。

設定APIの `/api/v1` は現行APIのバージョンです。Social OAuthの開始は `POST /social/oauth/{provider}/connect/{guild_id}`（セッション、フォームの `csrf_token`、Guild管理権限が必要）、外部Providerのcallbackは `/social/oauth/{provider}/callback` です。

更新はrevisionで競合を検知します。長時間処理と配送はOutboxまたはScheduleへ保存し、Leaseを取得したProcessが実行します。期限切れLeaseは再取得でき、外部Event IDやInteraction IDの一意制約で重複処理を防ぎます。

## Outbox・Schedule実行基盤

`jobs/models.py` はClaim・Outcome・JobStore Protocol、`jobs/repository.py` はSQLと所有権検査、`jobs/runner.py` は取得・更新・実行・完了の順序を担当します。Domain RepositoryがQueueSpecを持ち、既存テーブルのPayloadを保持します。

共通Runnerの対象はTicketのOutbox/自動Close Schedule、Reaction RolesのOutbox/期限Schedule、Socialイベント配送、ModerationのDashboard要求/期限付き処置、Suggestions配送の8 Queueです。継続監視するSocial ProviderのCursor/Polling、Panel公開、Lockdown復元はDomain側のライフサイクル処理であり、この有限ジョブQueueとは別です。

- 1件ずつ取得し、処理中はLease期間の1/3ごとに更新します。PostgreSQLの`FOR UPDATE SKIP LOCKED`で取得するため並行実行でも同じジョブを取得しません。
- 完了・更新にはID、所有者、取得ごとのToken、有効期限、processing状態の一致が必要です。同じ所有者名で再取得しても古いTokenは拒否します。Lease喪失時はHandlerをキャンセルし、そのBatchを終了します。次の定期実行は継続できます。
- 取得時に試行数を加算し、最大8回。再試行待ちは `min(3600, 15 × 2^attempt)` 秒。最終試行でProcessが停止した場合も、Lease失効後の取得処理でfailedへ終端化します。failed行がDead Letterで、勝手に再実行しません。
- completed/done/failedは終端日時から30日保持し、Batch開始時に削除します。保留・実行中の行は保持期限の対象外です。PostgreSQL初期SchemaにToken・試行数・終端日時・検索Indexを含みます。
- Queue内の重複実行防止と外部APIの副作用の一回性は区別します。Discord成功直後の停止はDomainの配送記録・補償で扱います。既にModeration実行イベントがある未完了要求は成功に丸めず、照合が必要なfailedとして残します。

Actionの部分失敗は成功扱いに丸めず、各結果と復旧可能性を保存します。Discord Resource作成後にDB更新が失敗した場合は孤立Resourceとして記録します。


## Discord操作の分離

`discord_io/` は再試行可否・部分失敗・Resource不在を表す共通例外を定義します。Domainごとの `discord_adapter.py` がSDK操作を実装し、ServiceはID・値・Portを使って状態遷移を決めます。CogはInteraction応答とEventの受付を担当し、対象Domainの外部Resource操作はServiceとAdapterへ委譲します。

- `moderation/contracts.py` は処置の値とPort、`moderation/discord_adapter.py` はDiscord型からの変換と実操作です。既存 `moderation/adapter.py` は将来のDiscord AutoMod同期向け契約で、イベント入力変換ではありません。
- `ticketing/panel_delivery.py` はPanelの公開・投稿ID保存・旧投稿削除・完了の順序を担当します。Lease所有者は取得ごとに一意で、完了時に期限とrevisionも照合します。投稿結果が不明な場合はAdapterがBot自身の識別印を履歴から探し、照合できなければ重複投稿せず `publishing` を保持します。履歴照合は直近200件です。投稿IDが未確定のまま削除要求を受けた場合は `delete_uncertain` を保持し、投稿IDを照合・保存してから削除します。
- Ticket Claimは変更前後の権限を `claim_started` として保存してから実行します。ClaimのDB確定と `claim_finished` は同一Transactionです。補償失敗は未解決の操作として残し、起動時に復元を再試行します。現在の権限が保存した変更前後のどちらとも異なる場合は自動上書きを止めます。
- TicketのClose確定時に `close_resource` Outboxを同じTransactionで作ります。Transcriptがあり、Ticketが閉じた状態でrevisionも一致する場合だけ、Adapterが削除またはThreadのArchiveを実行します。再開後の古い削除ジョブは拒否します。
- Social Provider監視は取得ごとに一意な所有者値を発行します。完了・削除は有効なLeaseだけが可能で、取得したEventの保存とCursor更新も同じTransactionです。

受入状態と検証結果は[実行計画](EXECUTION_PLAN.md)で管理します。


Ticketの返信・Staff NoteはServiceが復号・配送Intent・記録を担当し、AdapterがDiscordへ投稿します。配送KeyはOutbox IDと作成日時の組で、保持期限後に数値IDが再使用されても以前の配送と混同しません。結果不明の場合は識別印を照合し、明確な未送信エラーだけ新規送信として再試行します。内部Noteは同じ配送Keyの保存済み行を再利用します。

Ticket参加者の変更と回答待ちCategoryの移動・復帰もOutbox経由です。Categoryの移動前後はAPI呼出し前に監査記録へ保存し、DB更新に失敗しても元のCategoryを保持します。現在のCategoryが記録した移動前後のどちらでもなければ、自動移動を止めます。

Ticket作成はInteractionに対応する既存Resourceを再利用し、結果不明の作成を繰り返しません。作成Intentが残るTicketは起動時にChannelのTopic、またはPrivate Threadの識別名・親Channel・Bot所有者を照合します。候補が一意でなければ人手確認が必要です。ChannelとThreadの作成後にID保存が失敗した場合も、照合したResourceを孤立Resourceの復旧経路へ戻します。

### DomainとDiscordの境界

| Domain | 状態遷移・復旧 | Discord操作 |
| --- | --- | --- |
| Moderation | `moderation/service.py`、値とPortは `contracts.py` | `moderation/discord_adapter.py` |
| Ticket | `ticketing/service.py`、Panel公開は `panel_delivery.py`、通知内容は `messages.py` | `ticketing/discord_adapter.py` |
| Reaction Roles | `reaction_roles/service.py`、配送は `delivery.py`、Role変更と補償は `roles.py` | `reaction_roles/discord_adapter.py` |
| Social | `social/service.py`、Provider監視は `worker.py` | `social/discord_adapter.py` |
| Suggestions | `suggestions/service.py`、配送は `delivery.py` | `suggestions/discord_adapter.py`、Embed/View組立ては `presentation.py` |

CogはInteractionへの応答と入力変換を担当し、外部Resourceへの操作をAdapterへ渡します。Domain ServiceはDiscord SDKやFastAPIの型をImportしません。将来のNative AutoMod同期契約である `moderation/adapter.py` は、実際のDiscord入出力を担当する `discord_adapter.py` とは別です。

TicketのWelcome・Staff通知・Close DM/Log・Open Mention除去はOutboxで配信します。Resourceの有効化とWelcome予約、Closeと削除・通知予約はそれぞれ同じTransactionです。Close通知はその時点のTranscript IDと理由を保持し、後の再開で内容を取り違えません。

Suggestionsは投稿予約を提案作成と、表示更新・審査通知の予約を投票/審査と同じTransactionに保存します。外部投稿前のIntentと、投稿後のID保存はOutboxのToken・期限を検査します。投稿ID保存後は表示更新を予約します。不明な配送は識別印を照合し、照合できない場合は再投稿しません。

### Resource所有権と復旧時の扱い

`jobs/repository.py` のResourceLeaseRepositoryが所有権の保存と検査、`jobs/leases.py` が非同期処理中の更新・中断・解放を担当します。`resource_leases`をLockdownのGuild、TicketのClaim、Reaction RolesのGuild/Memberに適用します。開始・復旧・期限処理は同じResourceのLeaseを共有し、旧所有者による状態確定と補償を拒否します。DiscordのAPI自体にはDBのTokenを渡せないため、結果不明の外部処理は記録を使って照合します。

Reaction Rolesは変更前後のRole一覧を保存してから操作し、Assignment・Binding・期限・リアクション除去予約と完了記録を一括確定します。補償には直近100件の監査ログでBot自身とOperation IDを確認します。人手の変更や証拠不足を検出した場合は補償待ちを残します。`View Audit Log`がない場合も成功扱いしません。

Lockdownは全対象の復元情報を保存してから権限を変更します。復元時は現在値が変更前なら復元済み、適用値なら復元可能、それ以外は競合です。すべての復元が確定した時だけLockdown完了と対応するRaid状態解除を同じTransactionに保存します。失敗・競合ではactiveとlast_errorを維持します。

復旧が保留された場合は、機能別の監査記録、対象Resource、Botの権限、投稿の識別印を照合してください。直近200件の投稿に証拠がない場合や権限不足の場合、結果不明の投稿を自動的に作り直すことはありません。現在の復旧機能と実Discordでの運用検証は区別し、Stageの未検証をローカルの契約テスト成功で代替しません。


## Domain API Router

`dashboard/api/context.py` はアプリごとのRepository・Service・Discord API参照を生成します。RouterはContextを引数で受け取り、`dashboard/app.py` のGlobalや環境変数を参照しません。ModuleのImport時にはDB接続やTranscriptディレクトリを作りません。

| ファイル（`dashboard/api/`） | 責務 |
| --- | --- |
| `session.py` / `guilds.py` | Session・個人設定・利用可能Guild、Guild概要・機能・Resource一覧 |
| `modules.py` / `engagement/suggestions.py` | 汎用ModuleとSuggestions専用API |
| `social/providers.py` / `moderation/` / `community/reaction_roles.py` | 各機能のHTTP入力・応答・Repository/Service呼出し。ProviderとルールFamilyの共通経路はカテゴリーで一度登録 |
| `community/ticket_support/configuration.py` | Ticket設定・Form・Team・Panel・Tag・統計 |
| `community/tickets.py` | Ticket Inbox・操作・返信・Transcript・添付・Feedback |
| `dependencies.py` | サーバー側Session、Guild管理権限、CSRF。公開OAuth開始も同じ検証を利用 |
| `community/ticket_support/dependencies.py` | Ticket Staff、担当Team、Guild所属の認可 |
| `resources.py` / `community/ticket_support/resources.py` | Guild Resourceの共通Indexと所属・権限検査、Ticket固有制約 |
| `errors.py` | HTTPエラー・revision競合・If-Matchの検査 |
| `serialization.py` / `community/ticket_support/presentation.py` / `features.py` | 公開ID・Ticket・Featureの表示用変換 |

FastAPI `Depends` はSession、管理権限、Ticket Staff、CSRFの入口を表します。既存のエラー優先順が必要なRouteは同じDependencyのメソッドを明示呼出しします。更新時のGuild管理権限とResourceはキャッシュを使わず取得します。Ticket操作では担当Teamの所属も再確認します。明示的なTeam user IDが残っていても、Guild所属を取得できないユーザーにはStaff権限を与えません。Transcript/添付の申請者本人の閲覧権限は別経路として維持します。

分割前に固定したOpenAPI（59パス）と認証・認可・CSRF応答（199ケース）を `tests/fixtures/api_v1_contract.json` で比較します。P2-6で公開Schemaと入力制約を追加し、エラーEnvelope・Discord ID文字列・内部ID整数・一覧のnextをFrontendと同時に統一しました。元のFixtureは保持し、意図した契約変更を比較側で明示しています。


## API SchemaとUIの構造

| 配置 | 責務 |
| --- | --- |
| `dashboard/api/schemas/` | Domain別の公開DTOと入力制約。Domain自体はHTTP Modelに依存しない |
| `dashboard/api/body.py` / `route.py` | JSON入力検証とOpenAPI記述、共通エラーEnvelope |
| `scripts/generate_api.py` | 実RouterからOpenAPI、操作別TypeScript型、入力制約を再現可能に生成 |
| `dashboard/frontend/src/generated/api.ts` | 自動生成物。手書きのDTOを重複管理しない |
| `dashboard/frontend/src/api.ts` | Session/CSRF、型付きHTTP操作、項目エラー、204/添付Blobの処理 |
| `dashboard/frontend/src/App.tsx` | Session取得と最上位Route |
| `dashboard/frontend/src/app/` | Shell、Navigation、Account、個人表示設定 |
| `dashboard/frontend/src/routing/` | RegistryからRoute、Navigation、検索、パンくずを組立てるアプリ構成層 |
| `dashboard/frontend/src/features/<category>/` | 機能入口と専用画面。community配下のTicket/Reaction Roles、engagement配下のSuggestions、moderation/socialの画面 |
| `dashboard/frontend/src/components/` | SaveBar、ResourcePicker、AccessPolicy、PermissionDiagnostics、Embed、Schedule、状態表示 |
| `dashboard/frontend/src/components/forms/` | 入力Field・Toggle・FormFieldsEditor、生成制約からHTML属性への変換 |
| `dashboard/frontend/src/locales/{ja,en}/` | common・moderation・tickets・reactionRoles・social・suggestionsの翻訳Namespace |

RootとDomain Routerは `React.lazy` / `Suspense` で画面を遅延読込みします。画面からメタデータだけをImportして依存DomainのUIまで読み込まないよう、catalogを分離しています。翻訳はNamespaceごとにファイルを分け、現時点では初期化時に全Namespaceを登録します。Namespaceのネットワーク遅延取得は行いません。

共通UIは値・変更コールバック・見出し等を受け取り、Domainの保存処理を持ちません。例えばEmbedのTicket変数案内とScheduleの見出しはTicket画面から渡します。SaveBarは通常の保存CallbackとHTML form属性によるsubmitの両方に対応し、必須入力のブラウザー検証を維持します。409や権限喪失で編集内容を破棄せず、再試行・再読込を利用者が判断できます。

設定状態は `components/feature/ConfigurationState.tsx` がMetadataの保存値・親機能・必須項目・不足権限とResource一覧を照合します。特殊なResource項目はRegistryのfields宣言を渡します。Domainの稼働を推測する共通Serviceは作らず、ルール有効件数・Provider可用性・公開状態は各画面が既存APIから表示します。設定ON、公開済み、アカウント確認済みは実行・配送成功の証明ではありません。Ticket Staffの画面では管理Metadata・Resource取得と設定状態表示を行いません。

`components/forms/useSettingsDraft.ts` は取得値・編集値・編集開始時のrevisionを分けます。未編集の再取得は反映し、編集中は入力を保持して変更通知を出します。破棄は最新取得値、成功は保存応答を次の基準にします。`useSaveMutation.ts` はReactの再描画前の重複送信も抑止し、API入力・成功後のcache更新/再取得は呼出元が所有します。React Hook Formの画面は同じ契約をresetとdirty状態で実現します。

アプリ入口はData Routerを使用し、`NavigationGuard.tsx` の一つのBlockerが各 `useUnsavedChanges` の編集状態を集約します。リンク・検索の命令的遷移・履歴移動を保護し、保存中は移動を抑止します。保存成功後の意図した遷移だけを呼出元が明示的に許可します。タブ終了/再読込はbeforeunloadで保護します。認可は引き続きAPIの責務です。401は既存の再ログイン経路を維持し、Draftの永続保存は行いません。

ルール一覧の既存削除APIは逐次処理です。成功済みIDをpendingから除き、失敗時は削除済み件数・残りの変更・元revisionを保持します。破棄で成功済み削除を復元しません。これは全件原子的なルール一括状態変更APIとは別契約です。

ModerationのFamily/Trigger選択・未保存の無効テンプレート・有効化時の検証は `moderation/rules.py` が所有します。一括状態変更はRepositoryが既存CRUDと同じGuild Moduleロックを取得し、選択全件の所属/revision/設定を確認してからenabledだけを更新します。変更された行のrevisionとModuleのrules_revisionを同時Commitし、Runtimeのキャッシュ再取得を促します。後半の保存失敗も全件Rollbackします。既存ルールの内容・順序・履歴と親/Familyの有効状態は保持します。HTTP契約は[API](api.md)、受入は `tests/test_rule_operations.py` を参照してください。

`components/feature/ModuleSettings.tsx` は共通Module APIの保存・状態表示を担当し、項目描画・説明・追加操作をpropsで受け取ります。成功時は応答のrevisionを次回保存へ渡し、失敗時と編集中の再取得では入力を保持します。`components/ui/Button.tsx` は既存Tokenのvariant、loading、disabled、form/type、aria/refを扱います。`components/editors/EmbedEditor.tsx` は値と制約・変数候補を受け取り、Ticket側が生成API制約と保存を所有します。共有部品から機能モジュールへ依存しません。

視覚仕様は `design.md` と既存Tokenを維持します。Playwrightは別の一時出力先へbuildしたSPAをpreviewで配信し、開発サーバーの初回変換時間と画面の動作を切り分けます。本番の `/ui/` buildとは出力先を分け、4画面幅、日英、3外観×light/dark、保存・再読込・競合・権限・キーボード・Accessibilityを検証します。


## Moderationルールの操作画面

`ruleScreen.tsx` はFamilyごとの作成画面を既存FeaturePageのactionとして登録し、静的な `rules/new` はRegistryが合成します。既存詳細URLは機能内Routerが扱います。`RuleEditor` はGuild/Family/ID/複製元でDraftを分離し、`?copy=<id>` を未保存・無効・Identityなしの新規入力へ変換します。保存は既存POST、編集はrevision付きPUTです。即時保存duplicate APIはこのUIで使いません。

テンプレートはBackendから取得し、読込失敗では入力を保持します。明示的な既定値読込は置換確認後に適用し、検知方法だけの切替はそのTriggerのconfig/event_typeを差し替えます。`ruleForm.ts` はDomain項目を明示的に送信し、画面補助値を除きます。編集対象外のconditions/exemptions/Trigger固有値を保持し、複製では元のID/revision/時刻を持ち込みません。

`RuleList` は順序・削除のdraftと、一括変更の選択スナップショットを分け、両操作を同時に保存させません。`RuleBulkDialog` は件数、モード、権限、Resource・親停止・入力不足を確認し、状態更新を単一リクエストで送ります。409の選択/revisionは黙って上書きせず、明示再取得後に再確認を求めます。保存中の再送信・画面移動を共通hookで保護します。表示上の条件確認はAPI認可や実行時のResource/Role階層検査を代替しません。

## DB時刻と障害境界

保存時刻・Lease期限はアプリがUTC epoch秒で生成し、接続SessionのTimezoneもUTCに固定します。Bot・Dashboard・Workerを動かすHostの時計を同期してください。テストだけはQueue/Resource Leaseの時計を注入して失効を再現します。

TransactionはRepositoryのDB操作で閉じ、DiscordやProviderへの通信を行う間は保持しません。psycopgのIntegrityError、接続断、LockNotAvailable、DeadlockDetectedを呼出元へ伝え、接続層が処理全体を勝手に再実行することはありません。Queueの再試行は既存のToken・Receipt・補償を通り、外部副作用の結果が不明な場合は照合を先に行います。接続断時の未Commit変更、lock timeout、deadlock被害側のTransactionはRollbackされます。

SocialのTarget作成・Alias統合・孤立Target削除はProvider単位のTransaction Advisory Lockを共有します。複数Workerが同じ外部Accountを同時解決しても、Subscriptionが一つのCanonical Targetへ集約されます。

## 運用復旧の構造

復旧処理は`recovery/`に暗号化BlobのArchive・復号/Hash検証とone-shot CLIを置き、`deploy/recovery.py`がComposeの停止・Snapshot・別Project復元・起動保留・解放を調整します。`deploy/recovery-db.sh`はPostgreSQL公式Image内のDBツールだけを呼び、アプリImageへDB Server/Clientを追加しません。`scripts/recovery.py`が運用者の入口、`scripts/verify_recovery.py`が実コンテナでの復旧契約検証です。

## 運用監視の構造

`observability/`に運用観測を集約します。`repository.py`はHeartbeat保存とDB/Queue集計、`heartbeat.py`は各イベントループからの定期送信とコンテナprobe、`metrics.py`は数値Counter、`http.py`はHealth/認証付きメトリクスとHTTP計測、`export.py`はPrometheus形式、`logging.py`は許可した項目だけのJSONログ、`configuration.py`はHTTP/CLI共通閾値を担当します。

接続層とJobsは軽量な`metrics.py`だけを参照し、HTTPや監視Repositoryに依存しません。Queueのテーブル・列対応は`jobs/catalog.py`をDomain Repositoryと監視で共有し、SQL命名の重複を避けます。`runtime_heartbeats`はService/起動Instance単位で保存し、DB時刻と最新Instanceのready状態から停止を判定します。公開APIのOpenAPI契約には監視入口を追加しません。運用方法と限界は[監視と障害対応](../operator/monitoring.md)を参照してください。
