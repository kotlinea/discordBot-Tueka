# アーキテクチャ

## 境界

- **Repository**：SQLiteへの読書き、Transaction、Lease、Revision
- **Service**：検証、状態遷移、冪等性、権限に依存しない業務処理
- **Discord Adapter / Cog**：Discord Event、Interaction、Permission、API操作
- **Dashboard API**：OAuth、CSRF、Guild所属、Payload Validation
- **Worker**：外部Provider、Cursor、Webhook購読、Polling

## 共通パターン

DashboardのSession・Discord OAuth state・ユーザー個人設定は `dashboard/repository.py` が保存します。Web画面とJSON APIはこのRepositoryを直接使用します。

Guild Moduleの汎用CRUD・有効Guild一覧は `guild_settings/repository.py`、既定値・正規化は `guild_settings/models.py` が担当します。APIとCogは設定Repositoryと各DomainのRepositoryを直接使用します。旧 `storage.py` とGuildStorageの委譲窓口はありません。

| ディレクトリ | 責務 |
| --- | --- |
| `dashboard/` | Session、Discord OAuth state、個人設定、HTTP/APIの入口 |
| `guild_settings/` | Moduleの有効化、設定の正規化、保存・revision |
| `community/` | 一時VC、テキストXP・音声XP、ランキングの保存 |
| `engagement/` | Pollと投票、期限切れの保存処理 |
| `social/` | Repository、モデル、Token暗号化、Provider、Webhook検証、Worker実装 |
| `moderation/` | Repository、ルール検証・評価、Discord入力変換、処置Service。Case、Trust、証拠、Lockdown、期限処理もこのDomainに含む |
| `ticketing/` | Ticketのモデル、Repository、Service、暗号化Transcript |
| `reaction_roles/` / `suggestions/` | 各機能のモデル、Repository、Service |
| `cogs/` | Discordに登録する各Domainの入口。設定とDomain保存を明示的に利用 |

Moderationのルール更新と設定のrules_revision更新、CaseとTrustイベントの記録は同じTransactionを維持するため `moderation/repository.py` がまとめて扱います。一般的な設定保存をこの経路へ集約しません。TicketのBlacklist・当番・Tag・Panel移動・自動Close除外・削除記録もRepositoryが扱い、ServiceやCogから直接SQLを実行しません。

`social_worker.py` は従来の起動コマンドを保つ薄い入口で、処理本体は `social/worker.py` です。APIの内部生成関数はDBパスを受け取り、DomainごとのRepositoryを生成します。HTTP URLと認可の契約は維持します。共通Outbox/Runnerは `jobs/` にあります。Discord操作のAdapterへの分離はP2-4で進めており、API Routerの分割は後続の実行単位です。

SQLite接続・Transaction・WAL・busy timeout・Backup・Schema適用済み検査は `database.py` に集約しています。全DomainのRepositoryはこの接続を使います。書込み待ちは共通で10秒です。更新処理の必要に応じてRepositoryが `BEGIN IMMEDIATE` を選択します。

Schemaは番号付きMigration CLIだけが作成・変更します。RepositoryのコンストラクタはDDLを実行せず、未適用・不一致の履歴を検出すると `SchemaNotReady` で失敗します。BotはDiscord接続前、Dashboard / Workerは保存層の作成時に確認します。現行Ticketの未完了Close復旧やReaction Rolesの不足設定修復は、Schema変更とは別のDomain処理として保持しています。

認証後の管理画面はReact SPAを常時配信します。Dashboard切替Flagや旧管理フォームはありません。公開ランディングと404画面のみJinjaを使用します。Frontendをbuildしていない場合、管理画面は503を返します。

設定APIの `/api/v1` は現行APIのバージョンです。Social OAuthの開始は `POST /social/oauth/{provider}/connect/{guild_id}`（セッション、フォームの `csrf_token`、Guild管理権限が必要）、外部Providerのcallbackは `/social/oauth/{provider}/callback` です。旧管理フォームの `/servers/{guild_id}/social/connect/{provider}` は廃止しています。

更新はrevisionで競合を検知します。長時間処理と配送はOutboxまたはScheduleへ保存し、Leaseを取得したProcessが実行します。期限切れLeaseは再取得でき、外部Event IDやInteraction IDの一意制約で重複処理を防ぎます。

## Outbox・Schedule実行基盤

`jobs/models.py` はClaim・Outcome・JobStore Protocol、`jobs/repository.py` はSQLと所有権検査、`jobs/runner.py` は取得・更新・実行・完了の順序を担当します。Domain RepositoryがQueueSpecを持ち、既存テーブルのPayloadを保持します。

共通Runnerの対象はTicketのOutbox/自動Close Schedule、Reaction RolesのOutbox/期限Schedule、Socialイベント配送、ModerationのDashboard要求/期限付き処置、Suggestions配送の8 Queueです。継続監視するSocial ProviderのCursor/Polling、Panel公開、Lockdown復元はDomain側のライフサイクル処理であり、この有限ジョブQueueとは別です。

- 1件ずつ取得し、処理中はLease期間の1/3ごとに更新します。SQLiteの書込みTransaction内で取得するため並行実行でも同じジョブを取得しません。
- 完了・更新にはID、所有者、取得ごとのToken、有効期限、processing状態の一致が必要です。同じ所有者名で再取得しても古いTokenは拒否します。Lease喪失時はHandlerをキャンセルし、そのBatchを終了します。次の定期実行は継続できます。
- 取得時に試行数を加算し、最大8回。再試行待ちは `min(3600, 15 × 2^attempt)` 秒。最終試行でProcessが停止した場合も、Lease失効後の取得処理でfailedへ終端化します。failed行がDead Letterで、勝手に再実行しません。
- completed/done/failedは終端日時から30日保持し、Batch開始時に削除します。保留・実行中の行は保持期限の対象外です。Migration 0008でToken・不足列・検索Indexを追加します。
- Queue内の重複実行防止と外部APIの副作用の一回性は区別します。Discord成功直後の停止はDomainの配送記録・補償で扱います。既にModeration実行イベントがある未完了要求は成功に丸めず、照合が必要なfailedとして残します。

Actionの部分失敗は成功扱いに丸めず、各結果と復旧可能性を保存します。Discord Resource作成後にDB更新が失敗した場合は孤立Resourceとして記録します。


## Discord操作の分離（P2-4実装中）

`discord_io/` は再試行可否・部分失敗・Resource不在を表す共通例外を定義します。Domainごとの `discord_adapter.py` がSDK操作を実装し、ServiceはID・値・Portを使って状態遷移を決めます。CogにはInteractionの応答と、まだ移設していない操作が残っています。

- `moderation/contracts.py` は処置の値とPort、`moderation/discord_adapter.py` はDiscord型からの変換と実操作です。既存 `moderation/adapter.py` は将来のDiscord AutoMod同期向け契約で、イベント入力変換ではありません。
- `ticketing/panel_delivery.py` はPanelの公開・投稿ID保存・旧投稿削除・完了の順序を担当します。Lease所有者は取得ごとに一意で、完了時に期限とrevisionも照合します。投稿結果が不明な場合はAdapterがBot自身の識別印を履歴から探し、照合できなければ重複投稿せず `publishing` を保持します。履歴照合は直近200件です。投稿IDが未確定のまま削除要求を受けた場合は `delete_uncertain` を保持し、投稿IDを照合・保存してから削除します。
- Ticket Claimは変更前後の権限を `claim_started` として保存してから実行します。ClaimのDB確定と `claim_finished` は同一Transactionです。補償失敗は未解決の操作として残し、起動時に復元を再試行します。現在の権限が保存した変更前後のどちらとも異なる場合は自動上書きを止めます。
- TicketのClose確定時に `close_resource` Outboxを同じTransactionで作ります。Transcriptがあり、Ticketが閉じた状態でrevisionも一致する場合だけ、Adapterが削除またはThreadのArchiveを実行します。再開後の古い削除ジョブは拒否します。
- Social Provider監視は取得ごとに一意な所有者値を発行します。完了・削除は有効なLeaseだけが可能で、取得したEventの保存とCursor更新も同じTransactionです。

これらは実装済みの境界です。P2-4全体の完了判定と検証結果は、実行計画と進捗記録で管理します。


Ticketの返信・Staff NoteはServiceが復号・配送Intent・記録を担当し、AdapterがDiscordへ投稿します。配送KeyはOutbox IDと作成日時の組で、保持期限後にSQLiteの数値IDが再使用されても以前の配送と混同しません。結果不明の場合は識別印を照合し、明確な未送信エラーだけ新規送信として再試行します。内部Noteは同じ配送Keyの保存済み行を再利用します。

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

`jobs/repository.py` のResourceLeaseRepositoryが所有権の保存と検査、`jobs/leases.py` が非同期処理中の更新・中断・解放を担当します。0010のLeaseをLockdownのGuild、TicketのClaim、Reaction RolesのGuild/Memberに適用します。開始・復旧・期限処理は同じResourceのLeaseを共有し、旧所有者による状態確定と補償を拒否します。DiscordのAPI自体にはSQLiteのTokenを渡せないため、結果不明の外部処理は記録を使って照合します。

Reaction Rolesは変更前後のRole一覧を保存してから操作し、Assignment・Binding・期限・リアクション除去予約と完了記録を一括確定します。補償には直近100件の監査ログでBot自身とOperation IDを確認します。人手の変更や証拠不足を検出した場合は補償待ちを残します。`View Audit Log`がない場合も成功扱いしません。

Lockdownは全対象の復元情報を保存してから権限を変更します。復元時は現在値が変更前なら復元済み、適用値なら復元可能、それ以外は競合です。すべての復元が確定した時だけLockdown完了と対応するRaid状態解除を同じTransactionに保存します。失敗・競合ではactiveとlast_errorを維持します。

復旧が保留された場合は、機能別の監査記録、対象Resource、Botの権限、投稿の識別印を照合してください。直近200件の投稿に証拠がない場合や権限不足の場合、結果不明の投稿を自動的に作り直すことはありません。現在の復旧機能と実Discordでの運用検証は区別し、Stageの未検証をローカルの契約テスト成功で代替しません。
