# 現行ファイル構成と責務

確認日: 2026-09-21。追跡対象の実装構成を示す。ローカルのvenv・node_modules・一時コピーは構成に含めない。詳しい処理契約は[architecture.md](architecture.md)を参照する。

| 入口・場所 | 責務と変更の起点 |
| --- | --- |
| `runtime/__main__.py`、`runtime/lifecycle.py` | bot/dashboard/social-worker/migrate/testの実行、Process終了とSignal |
| `bot.py`、`cogs/<category>/<feature>.py` | Discord接続、拡張登録、Event/Interactionの入力と応答。一般情報は `general.py`、共有実行は `moderation/runtime.py` と `social/delivery.py` |
| `config.py`、`features/` | アプリ設定の型、カテゴリー別の機能Metadata・Binding・Docs対応 |
| `cogs/community/welcome.py`、`guild_settings/community/welcome.py`、`dashboard/api/community/welcome.py` | welcomeのDiscord入力、設定モデル、登録用設定Factory。参加ロールは隣接するautorole Cog |
| `dashboard/app.py`、`dashboard/api_v1.py`、`dashboard/api/` | Web配信、OAuth、API Router合成、認可・入力検証 |
| `dashboard/repository.py` | Session、OAuth state、個人設定 |
| `dashboard/frontend/src/` | React UI。`routing/catalog.ts` は画面経路、`locales/` は翻訳 |
| `dashboard/frontend/src/components/{feature,ui,editors}/` | 共通設定画面、標準Button、値・制約を受け取るEmbedEditor |
| `tokens.css`、`design.md`（本書と同階層） | 共通視覚TokenとUI設計契約 |
| `guild_settings/<category>/<feature>.py`、`registry.py`、`repository.py` | 機能別の既定値・正規化、Domain内の明示登録、共通の保存・revision |
| `moderation/`、`ticketing/`、`reaction_roles/`、`suggestions/` | 各Domainのモデル、Repository、Service、Discord Adapter |
| `social/providers/<provider>.py`、`social/`、`social_worker.py` | Provider別取得と明示Registry、Token、Webhook、監視Workerと登録起動入口 |
| `community/`、`engagement/` | VC/XP/ランキング、Pollの保存と処理 |
| `database/`、`migrate.py`、`migrations/postgresql/` | PostgreSQL接続、明示Migration、論理Backup/Restore |
| `jobs/`、`discord_io/` | Queue/Lease実行、外部操作の共通例外 |
| `observability/`、`recovery/` | health/metrics/安全なログ、復旧の状態管理 |
| `deploy/`、`scripts/setup.py`、`scripts/deploy.py`、`scripts/recovery.py` | 環境設定、Compose構成、導入・配布・復旧CLI、Caddy生成 |
| `compose.tools.yaml`、`Dockerfile.tools`、`scripts/tools.py`、`scripts/docker_proxy.py` | 共通タスク、固定依存、成果物、Host/daemonパス対応 |
| `Dockerfile`、`Dockerfile.caddy-test` | 本番ImageとローカルHTTPS受入用Image |
| `tests/`、`.github/workflows/` | 専用DBのテスト、共通ComposeタスクのCI実行 |
| `docs/` | Dashboardから配信する日英利用者Docs |
| `handbook/operator/` | 導入・運用・保守手順 |
| `handbook/developer/`、`history/`（本書と同階層） | 現行開発仕様・作業指示、記録時点の証拠 |

`/api/v1` は現行API。`moderation/adapter.py` は将来のNative AutoMod同期用契約であり、稼働中のDiscord操作は `discord_adapter.py` が担当する。将来契約の存在を機能実装済みの証拠にしない。
