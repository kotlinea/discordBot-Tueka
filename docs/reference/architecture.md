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

`social_worker.py` は従来の起動コマンドを保つ薄い入口で、処理本体は `social/worker.py` です。APIの内部生成関数はDBパスを受け取り、DomainごとのRepositoryを生成します。HTTP URLと認可の契約は維持します。Service内のDiscord操作の追加分離、共通Outbox/Runner、API Routerの分割は後続の実行単位で行います。

SQLite接続・Transaction・WAL・busy timeout・Backup・Schema適用済み検査は `database.py` に集約しています。全DomainのRepositoryはこの接続を使います。書込み待ちは共通で10秒です。更新処理の必要に応じてRepositoryが `BEGIN IMMEDIATE` を選択します。

Schemaは番号付きMigration CLIだけが作成・変更します。RepositoryのコンストラクタはDDLを実行せず、未適用・不一致の履歴を検出すると `SchemaNotReady` で失敗します。BotはDiscord接続前、Dashboard / Workerは保存層の作成時に確認します。現行Ticketの未完了Close復旧やReaction Rolesの不足設定修復は、Schema変更とは別のDomain処理として保持しています。

認証後の管理画面はReact SPAを常時配信します。Dashboard切替Flagや旧管理フォームはありません。公開ランディングと404画面のみJinjaを使用します。Frontendをbuildしていない場合、管理画面は503を返します。

設定APIの `/api/v1` は現行APIのバージョンです。Social OAuthの開始は `POST /social/oauth/{provider}/connect/{guild_id}`（セッション、フォームの `csrf_token`、Guild管理権限が必要）、外部Providerのcallbackは `/social/oauth/{provider}/callback` です。旧管理フォームの `/servers/{guild_id}/social/connect/{provider}` は廃止しています。

更新はrevisionで競合を検知します。長時間処理と配送はOutboxまたはScheduleへ保存し、Leaseを取得したProcessが実行します。期限切れLeaseは再取得でき、外部Event IDやInteraction IDの一意制約で重複処理を防ぎます。

Actionの部分失敗は成功扱いに丸めず、各結果と復旧可能性を保存します。Discord Resource作成後にDB更新が失敗した場合は孤立Resourceとして記録します。
