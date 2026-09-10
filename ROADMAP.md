# Tueka 開発ロードマップ

この文書は、TuekaのV2完全移行、システムリファクタリング、Docker化、既存機能の改善、新機能開発を進める順序と判断基準を定める正本です。個別機能の仕様は公式ドキュメント、視覚仕様は`design.md`、現在の実装境界は`docs/reference/architecture.md`を参照します。

## 目標

- V1互換コードと移行用分岐を削除し、V2だけを実行する。
- Repository、Service、Discord、API、Worker、UIの責務を分離する。
- 開発、Stage、本番で同じコンテナイメージを使用する。
- 既存機能を実運用可能な品質まで仕上げてから、共通基盤を利用して新機能を追加する。
- 変更の完了条件をテスト、移行、運用、ドキュメントまで含めて定義する。

## 開発原則

1. **常に動作する状態を維持する。** 各Phaseは単独でリリース可能な単位に分割し、大規模な一括置換を行わない。
2. **削除を分離より先に行う。** V1を残したままV2を整理すると、不要な互換境界まで新構造へ持ち込むため、先にV1を除去する。
3. **Docker化を二段階で行う。** 最初にテスト用コンテナで環境を固定し、構造整理後にDev、Stage、本番の運用構成を完成させる。
4. **機能より共通能力を先に作る。** Access Policy、Resource Picker、Embed、Form、Outbox、Schedule、Auditを機能ごとに再実装しない。
5. **SQLiteの限界を推測で決めない。** 単一Host、単一Replicaを維持し、競合や遅延の実測値が移行条件を超えた場合だけPostgreSQLへ移行する。
6. **新機能は縦に完成させる。** DBだけ、Botだけ、画面だけの未完成状態を公開しない。

## 実施順序

### Phase 0 — 基準確立と作業保護

目的は、以後の削除とリファクタリングを安全に検証できる状態を作ることです。

- 現在の未コミット変更を機能単位で整理し、Suggestionsを含む進行中のV2実装を先に完成させる。
- Python 3.13を使用する最小Dockerfileを追加し、壊れているローカル`.venv`へ依存せずPythonテストを実行できるようにする。
- Python、Frontend、Docsの依存関係をLockし、クリーン環境で再現できることを確認する。
- 現在のPythonテスト、TypeScript型検査、Vitest、Frontend build、Docs build、Playwrightの成功数と所要時間を記録する。
- 現在のSQLiteをバックアップし、V2データとV1データを識別するInventoryを作成する。
- CIへPython 3.13、Windows smoke test、コンテナbuild、秘密情報混入検査を追加する。

完了条件：クリーンなDocker環境で全テストと全ビルドを再現でき、失敗がある場合は既知のBaselineとして記録されていること。

### Phase 1 — V2完全移行とV1削除

V1は開発段階で終了しており、本番互換要件として保持しません。V2の現行データは保持しますが、V1専用データの自動移行を今後のRuntime責務にはしません。

#### Dashboard

- `DASHBOARD_UI_V2`とGuild Allowlistを削除し、React Dashboardを常時有効にする。
- 管理画面用Jinjaテンプレート、旧CSS／JavaScript、旧POST保存Routeを削除する。
- 公開ランディングだけはDashboard V1とは別の公開画面として残してよい。認証後の管理画面はSPAへ統一する。
- V2が現在使用している正式URLは維持する。V1だけが使用したURLや互換Redirectは削除する。

#### Ticket・Reaction Roles・Moderation

- `TICKETS_V2`とGuild Allowlistを削除し、Ticket V2を常時有効にする。
- 旧Ticket作成処理、旧ボタン、旧コマンド委譲、`support_tickets`からの実行時移行、平文Transcript移行処理を削除する。
- 旧ボタン式Reaction Roles、Legacy表示、移行Wizard、旧公開コマンド、旧テーブル参照を削除する。
- 旧AutoMod listener、旧`automod_rules`評価、禁止語CSVの実行時Import、旧警告・旧イベント移行Fallbackを削除する。
- JSON V1移行が不要であることを確認した後、`migrate_json.py`と移行済み判定を削除する。

#### DBとDocs

- 削除対象テーブルと列を番号付きMigrationで除去する。Migration前に自動Snapshotを作り、失敗時はTransactionをRollbackする。
- `PROGRESS.md`、`DEPLOYMENT_TODO.md`、`FEATURE_MODULE_GUIDE.md`など一時互換文書を削除し、必要な内容だけ正式ページへ移す。
- `.env.example`、README、運用資料からV1用Flagと旧起動方法を削除する。

完了条件：RuntimeとDashboardからV1分岐がなく、V2だけでBot、Dashboard、Worker、全専用機能が動作すること。V1削除Migrationを空DBと既存V2 DBの両方で検証すること。

### Phase 2 — システムリファクタリング

機能動作を変えず、責務と依存方向を整理します。各Domainを順番に移し、全体を一度に移動しません。

#### 保存とMigration

- `storage.py`からDomain固有SQLをModeration、Social、Community、Engagement、Dashboard用Repositoryへ移す。
- 共通DB層はConnection、Transaction、WAL、`busy_timeout`、Migration、Backupだけを担当する。
- 各Repositoryのコンストラクタで`CREATE TABLE`や`ALTER TABLE`を実行せず、明示的なMigration CLIへ統一する。
- Revision、冪等Key、Retention、監査日時の型と命名を統一する。

#### 非同期処理

- Ticket、Reaction Roles、Social、ModerationのOutbox／Schedule実装に共通ProtocolとRunnerを導入する。
- Domain固有テーブルは維持できるが、Lease、Retry、Backoff、Dead Letter、Cancel、Retention、Metricsの動作は共通化する。
- Discord API失敗をRetry可能、恒久失敗、競合、補償失敗へ分類する。

#### Service・Discord・API

- ServiceはDiscord ObjectやFastAPI Requestへ依存させず、検証、状態遷移、冪等性を担当する。
- CogはInteractionとDiscord Eventを共通Eventへ変換し、Discord API操作はAdapterへ集約する。
- `dashboard/api_v1.py`をDomain Routerへ分割し、OAuth、CSRF、Guild所属、Resource検証、revision競合を共通Dependencyへ移す。
- APIのエラー形式、Pagination、revision、日時、ID表現を統一し、OpenAPIからTypeScript型を生成する。

#### Frontend

- `App.tsx`はShellとRouter定義へ縮小し、画面をDomainとRoute単位に分割する。
- Save Bar、Resource Picker、Access Policy、Form Builder、Embed Editor、Schedule Editor、Permission Diagnosticsを共通Componentにする。
- Route単位のcode splittingを導入し、翻訳辞書をNamespace単位に分割する。
- UI上の検証とServer検証を同じSchemaから生成し、保存後に「未設定」へ戻る種類の変換差異をなくす。

完了条件：新機能追加時に既存の巨大ファイルへSQL、API、画面を直接追記せず、Domain単位で実装できること。既存機能の公開動作とAPI応答をContract testで維持すること。

### Phase 3 — Dockerによる環境統一

Phase 0のテスト用コンテナを、本番運用可能な構成へ発展させます。

#### 共通Image

- DashboardとDocsをNode build stageで生成し、Python依存関係をPython builder stageで構築する。
- 最終ImageにはPython Runtime、アプリケーション、ビルド済みFrontend／Docsだけを含める。
- 同じImageを`bot`、`dashboard`、`social-worker`、`migrate`、`test`の別Commandで利用する。
- 非root、read-only root filesystem、`no-new-privileges`を既定にする。

#### 環境別Compose

- `compose.yaml`：共通Service、Network、named volume、Healthcheck。
- `compose.dev.yaml`：Source bind mount、Vite、Dashboard reload、開発用の隔離DB。
- `compose.stage.yaml`：本番Image、Stage専用Token／OAuth callback／Volume、公開前のMigrationとE2E。
- `compose.prod.yaml`：固定Image digest、Restart policy、Resource上限、Log rotation、Backup job。
- Dev、Stage、本番で`.env`、Compose project名、Network、Volumeを共有しない。

#### 永続データと起動

- SQLite、WAL／SHM、Ticket Transcriptを`/var/lib/tueka`のnamed volumeへ保存する。
- Windowsのbind mount、NFS、複数Docker Host間でSQLiteを共有しない。
- `migrate`が正常完了した後だけ3Serviceを起動する。
- DashboardへLiveness／Readiness、BotとWorkerへHeartbeat検査を追加する。
- SQLite Backup APIを使用するBackup／Restore用one-shot serviceを用意する。
- 最初の本番移行ではNginxとTLSをHost側に残し、Dashboardだけを`127.0.0.1:8000`へ公開する。

完了条件：同じImage digestがStageと本番で動き、空環境への導入、Upgrade、Backup、Restore、Rollbackを運用手順だけで完遂できること。

### Phase 4 — 既存機能の完成度とUX向上

新しい大機能を追加する前に、機能一覧を「安定」「改善中」「利用不可」に分類し、利用不可の設定を画面へ出さないようにします。

- Moderation：Rule previewの説明性、Case／Appeal導線、権限診断、監査突合、誤検知の取消を完成させる。
- Ticket：6タブ編集、Panel公開状態、Inbox、Claim、回答待ち、Transcript、Feedbackの一連操作を統合検証する。
- Reaction Roles：全Type、Emoji Picker、Role階層診断、期限処理、Link、修復操作を完成させる。
- Social：Target解決、Provider状態、Webhook／Pollの欠落補完、通知Preview、再試行を運用画面で追跡可能にする。
- Suggestions：審査理由、Status履歴、Discussion、実装済み通知、Dashboard管理を追加する。
- 一般設定：チャンネル／Role／EmojiをID入力させず、Discord Resource Pickerへ統一する。
- 全機能：空状態、権限不足、Resource消失、保存競合、部分失敗、復旧操作、対応Docs linkを揃える。

完了条件：管理者がDashboardだけで設定、診断、復旧を行え、通常運用でDBやログを直接編集する必要がないこと。

### Phase 5 — 新機能

新機能は共通基盤への再利用効果と運用価値の高い順に追加します。

1. **Forms / Applications**：Staff応募、認証、提携申請、イベント申請を共通Formと審査Workflowで扱う。
2. **Moderation Appeals / ModMail**：Case、Infraction、Ticketを接続し、異議申立てと再審査を扱う。
3. **Scheduled Messages / Events**：単発／定期投稿、Discord Scheduled Event、開始前通知を扱う。
4. **Suggestions Roadmap**：カテゴリ、タグ、重複統合、Discussion Thread、Kanban、実装済み通知を扱う。
5. **Starboard / Highlights**：複数Board、除外、編集／削除追従、Thread対応を提供する。
6. **Giveaways / Community Events**：応募条件、期限、複数当選、再抽選、監査を提供する。
7. **Server Insights**：本文を長期保存せず、Moderation、Ticket、Join／Leave、通知配送の運用指標を集計する。

音楽再生、任意コード実行Workflow、本文の外部AI分類、独自決済、根拠のないMicroservice／Redis／Kafka導入は当面対象外とします。

## 新機能の受け入れ条件

新機能は、次が同じ変更に含まれる場合だけ公開します。

- Feature Registryと権限定義
- 番号付きDB MigrationとRepository
- ServiceとDiscord Adapter／Cog
- OAuth、CSRF、Guild所属、revisionに対応したAPI
- 日本語／英語Dashboardとモバイル操作
- 空状態、権限不足、部分失敗、Retry／復旧
- Unit、Integration、API、Frontend、Accessibility test
- 日本語の正式Docsと英語の主要説明
- Retention、監査、Backup、無効化時の挙動

## リリース判定

各Phaseの終了時に次を確認します。

- 全自動テストとBuildが成功している。
- Migrationを空DB、直前Version、再適用の3経路で検証している。
- StageでOAuth、Discord command、Webhook、Outbox、Scheduleを実動確認している。
- Backupから別VolumeへRestoreできる。
- Error rate、Outbox滞留、SQLite lock時間、Worker heartbeatを確認できる。
- README、`.env.example`、公式Docsが実装と一致している。
- Rollback方法と、Rollbackで失われるデータが明記されている。

## 次に着手する作業

1. 現在のSuggestions差分を完成させてCommit可能な単位へ整理する。
2. Python 3.13のテスト用Dockerfileと`.dockerignore`を追加する。
3. コンテナ内で全Test／BuildのBaselineを取得する。
4. V1削除Inventoryを確定し、Dashboard、Ticket、Reaction Roles、Moderationの順で削除する。
5. V1削除後の小さくなったコードを基準にMigration基盤とRepository分割を開始する。

