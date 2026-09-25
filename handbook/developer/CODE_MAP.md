# 現行ファイル構成と責務

確認日: 2026-09-25。追跡対象の実装構成を示す。ローカルのvenv・node_modules・一時コピーは構成に含めない。詳しい処理契約は[architecture.md](architecture.md)を参照する。

| 入口・場所 | 責務と変更の起点 |
| --- | --- |
| `runtime/__main__.py`、`runtime/lifecycle.py` | bot/dashboard/social-worker/migrate/testの実行、Process終了とSignal |
| `bot.py`、`cogs/<category>/<feature>.py` | Discord接続、拡張登録、Event/Interactionの入力と応答。一般情報は `general.py`、共有実行は `moderation/runtime.py` と `social/delivery.py` |
| `config.py`、`features/` | アプリ設定の型、カテゴリー別の機能Metadata・Binding・Docs対応 |
| `cogs/community/welcome.py`、`guild_settings/community/welcome.py`、`dashboard/api/community/welcome.py` | welcomeのDiscord入力、設定モデル、登録用設定Factory。参加ロールは隣接するautorole Cog |
| `dashboard/app.py`、`dashboard/api_v1.py`、`dashboard/api/` | Web配信、OAuth、API Router合成、認可・入力検証 |
| `dashboard/repository.py` | Session、OAuth state、個人設定 |
| `dashboard/frontend/src/features/<category>/<id>.feature.tsx`、各 `registry.ts` | UIの機能入口。経路、lazy loader、表示権限、項目描画、表示カテゴリー・画面種別・内部ページ/操作入口を明示登録 |
| `dashboard/frontend/src/routing/` | 登録からGuild/Standalone Route、Navigation、検索、パンくずを組立て |
| `dashboard/frontend/src/app/`、`app/guilds/` | Session、Shell、個人設定、Guild選択・概要。`Information.tsx` はDiscord由来のサーバー情報。`locales/` は日英翻訳 |
| `dashboard/frontend/src/routing/WorkspaceNavigation.tsx`、`focus.ts` | 登録済み内部ページとグループのナビ、Overlay選択後の遅延画面へのFocus |
| `dashboard/frontend/src/features/community/tickets/Routes.tsx`、`reaction_roles/{Routes,Groups,Events}.tsx` | Ticketの動的受付詳細・Panel編集、RRの動的編集・Link Group・履歴。静的内部ページは各 `.feature.tsx` が登録 |
| `dashboard/frontend/src/features/community/{tickets,reaction_roles}/`、`engagement/suggestions/` | 専用APIを使う画面と入力状態。Moderation/Socialの共有画面は各カテゴリー内 |
| `dashboard/frontend/src/components/{feature,ui,editors}/` | 共通設定画面、標準Button、値・制約を受け取るEmbedEditor |
| `dashboard/frontend/src/components/feature/ConfigurationState.tsx`、`components/forms/{useSettingsDraft,useSaveMutation,useUnsavedChanges,NavigationGuard,EditNotice}` | 設定値と実行条件、編集中の再取得、保存重複防止、ルーター離脱保護、未保存表示。保存APIは機能側が所有 |
| `tokens.css`、`design.md`（本書と同階層） | 共通視覚TokenとUI設計契約 |
| `guild_settings/<category>/<feature>.py`、`registry.py`、`repository.py` | 機能別の既定値・正規化、Domain内の明示登録、共通の保存・revision |
| `moderation/`、`ticketing/`、`reaction_roles/`、`suggestions/` | 各Domainのモデル、Repository、Service、Discord Adapter |
| `ticketing/access.py` | SessionとTicket APIで共有するTeam所属判定の公開契約 |
| `social/providers/<provider>.py`、`social/`、`social_worker.py` | Provider別取得と明示Registry、Token、Webhook、監視Workerと登録起動入口 |
| `community/`、`engagement/` | VC/XP/ランキング、Pollの保存と処理 |
| `database/`、`migrate.py`、`migrations/postgresql/` | PostgreSQL接続、明示Migration、論理Backup/Restore |
| `jobs/`、`discord_io/` | Queue/Lease実行、外部操作の共通例外 |
| `observability/`、`recovery/` | health/metrics/安全なログ、復旧の状態管理 |
| `deploy/`、`scripts/setup.py`、`scripts/deploy.py`、`scripts/recovery.py` | 環境設定、Compose構成、導入・配布・復旧CLI、Caddy生成 |
| `compose.tools.yaml`、`Dockerfile.tools`、`scripts/tools.py`、`scripts/docker_proxy.py` | 共通タスク、固定依存、成果物、Host/daemonパス対応 |
| `Dockerfile`、`Dockerfile.caddy-test` | 本番ImageとローカルHTTPS受入用Image |
| `scripts/verify_runtime_image.py` | Image内の機能Binding・同梱境界、Migration、配信、Worker起動・終了の受入 |
| `tests/`、`.github/workflows/` | 専用DBのテスト、共通ComposeタスクのCI実行 |
| `tests/test_feature_extension.py`、`tests/test_feature_boundaries.py`、Frontend `src/test/feature{Extension,Boundaries}.test.*` | 仮機能・カテゴリーの登録/解除、実起動・Shell、依存境界の受入 |
| `docs/` | Dashboardから配信する日英利用者Docs |
| `handbook/operator/` | 導入・運用・保守手順 |
| `handbook/developer/`、`history/`（本書と同階層） | 現行開発仕様・作業指示、記録時点の証拠 |

`/api/v1` は現行API。`moderation/adapter.py` は将来のNative AutoMod同期用契約であり、稼働中のDiscord操作は `discord_adapter.py` が担当する。将来契約の存在を機能実装済みの証拠にしない。
