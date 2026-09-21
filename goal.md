# 機能中心の疎結合化ロードマップ

制定日: 2026-09-21。今回専用の一時計画。**G0〜G3完了、次はG4**。
調査対象: `2b7050cb26acc85ea6edba080d5bf2af55458a18`。開始時の作業ツリーは変更なし。

## 目的と適用範囲

Bot・APIとDashboardを、カテゴリーのフォルダーと機能ごとのファイルを入口に読める構成へ再編する。機能実装と登録を追加すれば、既存の起動処理・Router合成・Shellの分岐を編集せずに接続できる状態を目指す。

「原則2」は [ENGINEERING](handbook/developer/ENGINEERING.md) の2番目の原則「横方向の疎結合」として適用する。機能中心の配置と、Service / Repository / Adapter / Cog / APIの責務分離を両立する。カテゴリーは発見・登録・表示の単位であり、DBの所有権やTransaction境界を決めるものではない。

計画に沿って一会話につきG段階を一つ完了させる。実装段階では構造と登録経路を変更し、既存の機能ID、URL、コマンド、権限、設定・保存データ、表示と復旧の契約を維持する。新機能、UI再設計、DB移行、実環境への配布は別作業とする。

全体の順序・受入状態は [ROADMAP](ROADMAP.md) と [EXECUTION_PLAN](handbook/developer/EXECUTION_PLAN.md) が正本。本計画は追加の構造改善Gとして登録した。Phase 0〜2を未完了に戻さず、T1/C1/P3-Gの残作業やPhase 4・5の受入条件を置き換えない。

## G0時点の構造と変更の起点

| 現在の場所 | 確認した構造・課題 | 計画上の扱い |
| --- | --- | --- |
| `feature_registry.py` | Metadataと日本語表示文言を一括定義。DashboardのIcon定義を参照 | 機能別定義とカテゴリー登録へ分離し、UI検査はUI側に置く |
| `bot.py`、`cogs/` | Botが拡張を読み込む。`community.py`は統計と一時VC、`engagement.py`はPollとミニゲームを含む | 機能別のCog入口と登録から拡張を合成 |
| `dashboard/api_v1.py`、`dashboard/api/` | Domain Routerは分離済み。合成は列挙式、機能Payloadには機能ID別の保存先分岐がある | 機能定義がRouterと設定アクセス契約を提供 |
| `guild_settings/models.py` | 機能の設定初期値を集約 | 機能別の設定定義へ分け、保存処理を共通基盤に保持 |
| `frontend/src/routing/catalog.ts`、`app/Shell.tsx` | URL、Navigation、カテゴリー、Breadcrumb、lazy importに個別分岐 | UI Registryから共通組立て。Staff専用経路も維持 |
| `frontend/src/features/` | Domain別画面と汎用Module設定画面が共存 | カテゴリー配下に機能単位の入口を統一 |
| `frontend/src/components/` | EmbedEditor、SaveBar、入力部品等が既に共有化済み | 既存を活用し、Button等と配置・拡張契約を揃える |
| `moderation/`、`ticketing/`等 | 状態遷移・保存・復旧の所有境界がある | 表示カテゴリーを理由に境界を分解しない |

`frontend/src/` は `dashboard/frontend/src/` の略記。現在のDBはPostgreSQL、`/api/v1` は現行APIである。

## 目標の配置

以下は実装予定の構成。機能入口は一機能一ファイルとし、その実装が大きい場合は同じカテゴリー内の専用パッケージへ委譲する。すべての層を一ファイルへ詰め込まない。

```text
features/                           # Backendの機能構成
  contracts.py                     # Category/Featureの型（SDK・HTTP型なし）
  registry.py                      # 明示登録、重複・参照検証
  defaults.py                      # 共通既定値と差し替え契約
  community/
    registry.py
    welcome.py
    autorole.py
    leveling.py
    live_stats.py
    temporary_voice.py
    reaction_roles.py
    tickets.py
  engagement/
    registry.py
    advanced_polls.py
    suggestions.py
    minigames.py
  moderation/
    registry.py
    moderation.py
    automod.py                      # 他の既存機能もそれぞれ一ファイル
  social/
    registry.py
    youtube_updates.py              # Providerごとの既存機能IDを維持
cogs/<category>/<feature>.py        # Discord入力・応答
dashboard/api/<category>/<feature>.py # HTTP入力・認可・応答
moderation/, ticketing/, ...        # 業務Domain。所有契約を維持
database/, jobs/, discord_io/       # Backend共有基盤

dashboard/frontend/src/
  features/
    contracts.ts
    registry.ts
    community/
      registry.ts
      welcome.feature.tsx
      tickets.feature.tsx          # 機能の入口
      tickets/                     # Inbox、Panel等の専用画面
    engagement/registry.ts         # 配下にsuggestions.feature.tsx等
    moderation/registry.ts         # 配下にautomod.feature.tsx等
    social/registry.ts             # 配下にyoutube_updates.feature.tsx等
  components/
    ui/Button.tsx
    editors/EmbedEditor.tsx
    forms/                         # 入力、Field制約
    feature/                       # 共通設定画面・保存/状態表示
  app/                             # Session、Shell、Account、Guild選択
  routing/                         # RegistryからRoute/Nav/Breadcrumbを組立て
  generated/                       # API由来の生成型
```

Session、OAuth、Guild選択、health等のアプリ基盤は機能一覧から独立して組み立てる。一般コマンドやAIなど現在のFeature RegistryにないCogも棚卸し対象とし、基盤として残すものと機能へ登録するものをG0で明記する。孤立した入口を作らない。

G0で、Help/Ping/ユーザー・Guild情報を基盤、Echo/計算/Dice/Geminiを既存Bot専用機能として分類した。Bot専用BindingはDashboard Metadataを省略でき、公開24機能やGuildの有効化条件を増やさない。Pythonの機能入口と同名パッケージの衝突を避け、Ticket等の補助実装は `ticket_support/` に置く。詳細は[全入口対応表](handbook/developer/history/FEATURE_STRUCTURE_G0-2026-09-21.md)。

既存のカテゴリーID `community / engagement / moderation / social` と機能IDを維持する。カテゴリーと`parent`は別の関係として検証する。Social Providerの共通処理、ModerationのRule/Case/Trustなどは同じ所有Domainへ委譲する。

## 登録と依存の契約

1. Backendの機能定義はID、カテゴリー、親、翻訳Key、Docs、設定定義、必要権限を所有する。カテゴリー登録は表示順と明示的な機能一覧を持つ。最上位Registryはカテゴリーを列挙するだけにする。
2. Bot/API固有のBindingはCog loader、Router factory、必要な依存を指定する。DomainはRegistryやUIをImportしない。Metadata読込でSDKやRouter本体までImportせず、起動時に選択したProcessのBindingだけを解決する。Import時のDB接続・ディレクトリ作成・Task起動を禁止する。
3. FactoryにはProcessごとのContextを明示注入する。巨大なGlobalサービス検索や動的なフォルダー走査は導入しない。共有Domainの初期化・終了は一度だけ行い、複数機能からの二重Cog登録・Worker起動を防ぐ。
4. Frontendの機能定義は同じ機能ID、既存Route、lazy loader、Navigation/Breadcrumb、表示権限、必要Namespaceを持つ。Backendの設定・権限・API型を手書きで複製せず、APIのMetadataと生成型を使用する。UI非対応のBackend機能は理由を明示する。
5. ID重複、未登録カテゴリー/親、親の循環、Route衝突、コマンド衝突、存在しないloader、Docs/翻訳/必要UI定義の欠落をテストまたは起動前検証で失敗させる。登録順と既存URLの優先順位を固定する。
6. UIの表示制御は認可の代替にしない。Session・CSRF・Guild所属・管理者/Staff・申請者の確認はAPI境界に残す。無効化時の新規受付停止と既存Job/復旧処理の扱いを、各機能の現在の契約どおり維持する。

「登録だけで追加」は、機能実装を用意した後の接続作業を意味する。同じカテゴリーへの追加はBackend/UI各機能ファイルと各カテゴリーRegistryへの登録で完結し、共通起動・Shell・汎用Routerへの機能別分岐追加を不要にする。新カテゴリーはそのRegistryを作り最上位へ一度登録する。Migration、翻訳、Docs、業務テストなど必要な成果物は別途追加する。

## 共通基礎要素とオーバーライド

- Backendは既定の設定読取・正規化・保存・機能表示を小さな契約として提供する。既存設定で足りる機能は既定実装を使い、Ticket等は明示的な関数/Factory差し替えで専用Repositoryへ接続する。単一の継承ツリーや万能Serviceは作らない。
- Frontendは共通設定画面、保存状態、エラー表示を既定とし、fields、説明、追加操作、専用画面loaderを型付きprops/slotで差し替える。新機能は既定から必要部分だけオーバーライドして開始できる。
- Buttonはvariant、disabled、loading、type、form、aria属性を標準化する。HTMLのsubmit、Focus、keyboard、44pxの操作対象と既存Tokenを維持する。
- EmbedEditorは値、onChange、制約、変数候補、説明を受け取る。Ticket固有の変数、APIアクセス、保存処理は呼出元が所有する。既存Editorを移設・再利用し、同等品を新設しない。
- 認可、CSRF、revision、Transaction、Lease所有権検査はオーバーライドで無効化できる拡張点にしない。共通UIから機能モジュールへの逆依存を禁止する。
- 実在する単純設定と専用保存の2例で共通契約を確かめ、仮想的な将来機能だけのために抽象化を増やさない。

## 実行順序と完了条件

各段階は前段の受入後に進める。実装変更と移設に必要な文書更新を同じ単位で行う。

| ID・状態 | 作業・成果物 | 完了条件 |
| --- | --- | --- |
| G0 完了（ローカル検証済み） | [全入口対応表と固定baseline](handbook/developer/history/FEATURE_STRUCTURE_G0-2026-09-21.md) | 24機能/16拡張/8 Queue/59 APIパス・77操作/103コマンドを対応付け、指定6タスク成功。G0残作業なし |
| G1 完了（ローカル検証済み） | Backend/UIの型、カテゴリーRegistry、明示Binding、既定値・override境界 | 重複・循環・衝突・不正参照、副作用のないMetadata読込、Bot/API/UIの初期化を検証。[記録](handbook/developer/history/FEATURE_STRUCTURE_G1-2026-09-21.md)。G1残作業なし |
| G2 完了（ローカル検証済み） | `welcome`をBot→設定API→UIまで試験移行。Button/EmbedEditorと共通設定を整理 | 保存/再読込/失敗時入力保持/無効化と登録接続を確認。[記録](handbook/developer/history/FEATURE_STRUCTURE_G2-2026-09-21.md)。G2残作業なし |
| G3 完了（ローカル検証済み） | community→engagement→moderation→socialのCog/API、設定モデル、Providerを機能別へ移行。専用保存Factoryと登録Workerを接続 | Python401件・API・103コマンド・Restore/ツール・Image内401件成功。認可・revision・配送/復旧・Transactionを維持。[記録](handbook/developer/history/FEATURE_STRUCTURE_G3-2026-09-21.md)。G3残作業なし |
| G4 未着手 | G3と同じ順でDashboardを移行。汎用Moduleの機能分岐、Shell/Navigation/Breadcrumbの個別分岐を登録へ集約 | 全既存Routeと直リンク、Staff専用表示、遅延読込、日英、入力保持、モバイル/keyboardを維持 |
| G5 未着手 | 拡張性と境界の受入。テスト専用の仮機能・仮カテゴリーで登録手順を検証 | 共通Bot起動/API合成/Shellを編集せず追加・除去できる。未登録/重複は検出。共通基盤と他機能への逆依存なし |
| G6 未着手 | 旧登録・未使用経路の削除、現行開発資料・同梱指定の更新、最終回帰 | 静的参照だけでなく動的起動・生成・Image・運用入口を確認。全群CIとImage内動作の証拠を記録 |

G3のTicket移行前にG2のoverride契約を専用保存で再評価し、必要最小限の修正を行う。大きい機能の一括移設は避け、登録・入力境界・画面単位で差分を区切る。作業中の橋渡しImportが必要なら所有者と削除段階を記録し、G6で残さない。

## 検証計画

実行場所はリポジトリルート。以下の`<task>`を表のタスクへ置き換える。Host Python/Nodeは使わない。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build <task>
```

| 段階 | タスク・確認 |
| --- | --- |
| G0 | `check`、`test-python`、`typecheck`、`test-web`、`api-check`、`commands-check`で変更前を記録 |
| G1〜G3 | `test-python`、`api-check`、`commands-check`。Registry拒否系、Bot起動/終了、アプリ間Context分離、同一Transaction・Lease・再起動復旧を検証 |
| G2・G4 | `typecheck`、`test-web`、`build-web`、`test-a11y`。共通部品の実操作と機能画面、直リンク・404、401/403/409/422、無効化、日英を確認 |
| G5 | 登録のみで組立てる統合テスト。Domain→HTTP/SDK、共有UI→機能、カテゴリー間内部Importを境界検査で拒否 |
| G6 | `check-docs`、`build-docs`、`ci`、`build-image`→`verify-runtime`、`git diff --check`。CIに含まれる成功済み検査は追加変更がなければ繰り返さない |

公開契約は変更しない方針なので、`api-check`等の差分はまず移設による欠落として調査する。生成物やFixtureを更新して差分を隠さない。正式な契約変更が必要と判明した場合は本計画に理由・影響を記載して切り分ける。

失敗時は直前の移行単位で原因を修正する。戻す場合もその単位だけを対象とし、ユーザー変更やDB/Volumeを破棄しない。ローカル回帰、Remote CI、Linux Host、実Discord/OAuth/WebhookのStage受入は個別に記録する。

## 最終受入と一時ファイルの終了

- [x] 機能名からBackend/API/UIの入口と所有Domainを辿れる対応表がある（G0）。
- [ ] 新機能・カテゴリーの接続が登録に集約され、中央の機能別条件分岐を追加しない。
- [ ] 共通基礎要素の既定実装からoverrideで開始でき、専用処理が共通基盤へ漏れない。
- [x] Button/EmbedEditor等の共有部品が共通フォルダーにあり、業務保存を持たない（G2）。
- [ ] URL・コマンド・認可・データ・冪等性・復旧・見た目を維持した証拠がある。
- [ ] `CODE_MAP.md`、`architecture.md`、`extending.md`、必要な作業指示と全体実行計画を更新する。
- [ ] 確定した設計は現行handbookへ、実施結果・未検証は日付付きhistoryへ移す。本ファイルを参照するリンクを整理してから`goal.md`を削除する。

## 計画制定時の記録

AGENTS.md→HANDOFF/ENGINEERING/CODE_MAP/architecture、Backend/Web作業指示、extending/api/design、DOCUMENTATION/TESTING/TOOLS、ROADMAP/EXECUTION_PLANと対象コードを確認した。今回の成果物は本計画であり、実装受入状態は変更しない。

2026-09-21、Windows Host / Docker DesktopのLinuxコンテナで作業前`check`成功（exit 0）。ログ: `artifacts/check/20260921T052052-0939a2e5`。通常権限でDocker接続が拒否されたため、権限付きで再実行した。機能回帰、Linux Host、Remote CI、実Stageは今回未検証。文書検査結果は制定履歴に記録する。
