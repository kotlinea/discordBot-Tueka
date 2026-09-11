# Tueka 実行計画

策定日：2026-09-10。方針と実施順序の正本は [ROADMAP.md](../ROADMAP.md)。本書は、その方針を現在のコードに対応付けた作業計画であり、新しい公開仕様ではない。

## 現在地と次の実行順序（2026-09-11確認）

以下の初回調査表は策定時点の記録である。P0-1〜P0-4、P1-0、P1-1、P1-2はローカル実装・検証の完了記録を `PROGRESS0910.md` に保存している。次の着手はP1-3。遠隔本番へのMigrationとStage実動は未完了であり、ローカル検証とリリース判定を区別する。以下は依存順序と各単位の確認事項を保持した一覧である。

1. **P1-1を閉じる。** `dashboard/app.py` のSPA配信、管理テンプレート・旧資産・旧POST削除、API側へ引き継いだ入力・権限検証をレビューする。正式URL、OAuth、CSRF、Guild認可、未build時503、静的資産・Docsの回帰結果を揃え、進捗へ記録する。既存差分を保持し、P0からやり直さない。
2. **P1-2：Ticket。** `config.py` のFlagとAllowlist、Repository初期化時の `migrate_legacy`、Cogからの平文Transcript移行を除去する。旧テーブル削除Migrationを同じ単位に含め、V2 Ticket・暗号化Transcript・保留処理の保持と再起動後の旧Schema非復活を検証する。
3. **P1-3：Reaction Roles。** `reaction_roles/repository.py` の旧共有設定参照を含め、Legacy UI・Wizard・旧コマンドの利用箇所を除去する。共有 `guild_modules` 自体は他機能が利用するため一括削除しない。
4. **P1-4：Moderation。** `cogs/automod.py` の起動時旧移行とCSV読込みを除去する。旧Rule/Eventへの外部キーと参照を解消してからMigrationを適用し、現行Case・Point・処置履歴を保持する。
5. **P1-5をPhase 1の出口とする。** JSON移行・旧DDL・一時文書の残存を検査し、Bot・Dashboard・Workerを再起動してV1が復活しないことを確認する。その後にPhase 2のDomain分割へ進む。

各単位はコード・Migration・テスト・正式Docs・進捗記録までを一つのレビュー対象とする。遠隔本番DBのSnapshot/Inventory、StageでのDiscord・OAuth・Webhook実動は既存記録でも未検証であり、ローカル成功だけでリリース済みとは扱わない。Phase 2以降の実施方針・受入条件は後述を維持し、詳細な対象ファイルはPhase 1終了時に再確定する。

## 1. 判断と調査範囲

直近の目標は新機能追加ではなく、Phase 0の検証基盤確立とPhase 1のV1除去である。続いて責務を整理し、その構造を本番用コンテナへ載せる。既存機能の運用品質を満たしてからPhase 5へ進む。

README、ROADMAP、設計・アーキテクチャ・機能・運用資料、起動処理、保存層、主要Domain、API、React画面、CIとテスト定義を確認した。今回は静的調査と計画策定であり、テスト・ビルド実行、本番DB調査、Discord実機検証は行っていない。テストの存在を成功や機能完成の証拠とは扱わない。

| 確認事項 | 現状と計画への反映 |
| --- | --- |
| 作業ツリー | 調査開始時の `git status --short` は空。ROADMAPの「未コミットSuggestions差分」は現時点では見つからない。差分整理を機械的に実行せず、完成度確認と必要な修正に置き換える。 |
| Suggestions | `suggestions/`、`cogs/suggestions.py`、専用API、`Suggestions.tsx`、正式Docs、Domainテストがある。Phase 0では投稿・投票・審査・設定保存の現行範囲を確定する。 |
| V1 Dashboard | `dashboard/app.py` にV2 Flag、Guild Allowlist、Jinja管理画面と旧保存処理が残る。認証・公開画面・SPA配信を切り分けて削除する。 |
| Ticket | `config.py` にV2 Flag、`ticketing/repository.py` に旧Ticket移行、`cogs/tickets.py` に旧Transcript移行呼出しが残る。V2のデータと暗号化Transcriptを保全する。 |
| Reaction Roles / Moderation | APIのLegacy情報、Repositoryの旧設定参照、AutoMod起動時のCSV Import・移行呼出しが残る。利用箇所を追ってDomainごとに除去する。 |
| 保存・責務 | `storage.py` は1,630行、`dashboard/app.py` は1,261行、`dashboard/api_v1.py` は1,219行。RepositoryのコンストラクタDDL、Ticket Service内の直接SQLも残る。V1除去後に分離する。 |
| Frontend | `App.tsx` は331行だが複数画面と共通部品を圧縮した実装が集まる。行数を目標にせず、Domainと依存方向で分割する。 |
| 再現性 | Frontend / Docsの `package-lock.json` とPython 3.13のCIは既存。Python依存は範囲指定が中心。Dockerfile / Composeはファイル一覧で未確認。既存Lock・CIを活用して不足分を追加する。 |
| 検証手順 | CIは `unittest`、READMEは `pytest` を案内。実行コマンドを統一する。PlaywrightはVite / Docs previewを起動する構成で、本番Python配信・OAuthの統合検証は別に必要。 |
| 文書差異 | `design.md` にもV1ロールバックFlagが残る。時点記録は実際には `docs/PROGRESS0814.md`。ROADMAP記載のファイル名だけで削除を判断しない。 |

**維持する境界：** Reactの `src/api.ts` は `/api/v1` を使用している。このAPIバージョンはDashboard V1を意味しない。Router内部を分割しても現行URLを維持する。`guild_modules` やModerationの共有テーブルも名前や旧参照の存在だけで削除しない。

## 2. 直近の実行順序と成果物

各行をレビュー可能なPRの目安とする。規模が大きい場合はDomain単位にさらに分割する。実装担当がコード・テスト・Docsを揃え、レビュー担当が契約維持と削除範囲、運用担当がStage・復元結果を確認する。担当者名と日程は着手時に割り当てる。

| 順序 | 作業と主な対象 | 完了条件・成果物 |
| --- | --- | --- |
| P0-1 | Suggestionsの現行仕様と実装・テストの対応を確認。`suggestions/`、Cog、API、画面、Docsを対象に不足を修正する。 | 投稿、投票変更・取消、終端状態、権限、無効化、別Guild拒否、設定revision競合、初回配送失敗、再起動後ボタンを検証。日英ラベルと保存→再読込の一致を確認。審査理由・Kanban等は持ち込まない。 |
| P0-2 | Python 3.13テスト用Dockerfile、`.dockerignore`、Python Lockを追加。既存npm Lockを `npm ci` で検証。 | `.env`、DB、Transcript、バックアップ、依存ディレクトリをbuild contextから除外。クリーン環境でインストールできる。Python / Node / Lockの識別情報を保存。 |
| P0-3 | コンテナ内の全テスト・ビルドBaselineを取得し、CIへ反映する。 | 実行数・成功・失敗・skip・所要時間・Commit・コマンドを記録。Windows smoke、コンテナbuild、秘密情報混入検査を追加。失敗は原因・影響・対応作業へ紐付ける。 |
| P0-4 | 運用DBのBackupとV1削除Inventoryを作成する。 | SQLite Backup APIで整合したSnapshotを作り別DBへ復元。テーブル・列・読書き箇所・件数・外部キー・保持/削除・削除順を一覧化。機密の行内容はリポジトリへ入れない。 |
| P1-0 | V1削除に必要な最小の番号付きMigration実行基盤を用意する。 | 適用履歴、実行前Snapshot、Transaction、失敗時Rollback、再適用の安全性を検証。旧初期化処理が削除テーブルを再作成しないよう対応する。 |
| P1-1 | DashboardをSPAへ統一。Flag・Allowlist・旧管理テンプレート・旧POST・V1専用Redirectを削除する。 | 現行SPA URL、OAuth、CSRF、Guild認可、静的資産、Docs配信が動く。ランディングの依存資産は保持。V1専用URLが到達不能になる。 |
| P1-2 | TicketをV2へ固定。旧作成・ボタン・委譲・実行時移行を削除する。 | V2のPanel、受付中Ticket、Inbox、暗号化Transcript、Outbox、Scheduleを保持。空DB・既存V2 DB・混在Fixtureで検証する。 |
| P1-3 | Reaction Rolesの旧ボタン、公開コマンド、Legacy表示、Wizard、旧参照を削除する。 | 現行メッセージ・マッピング・付与状態・期限処理・修復操作が動く。共有設定を巻き込まない。 |
| P1-4 | Moderationの旧listener・評価・CSV Import・警告/イベントFallbackを除去する。 | 現行Rule、Case、Point、Event、処置、期限付き解除を保持。旧ID列の参照を解消してから削除する。 |
| P1-5 | JSON移行不要をInventoryで確定し、`migrate_json.py` と旧判定を削除。残存Schemaと資料を整理する。 | Bot / Dashboard / Worker再起動後もV1構造が復活しない。README、`.env.example`、`design.md`、起動・更新・復元手順を新CLIへ統一。旧文書の必要情報を正式ページへ移しリンクを修正する。 |

P0-3とP0-4の完了後に削除を始める。P1-0は破壊的Migrationを安全に行うための最小基盤であり、Phase 2の大規模Repository再編を前倒しするものではない。各Domainで最後の参照を除いた変更に、そのDomainの削除MigrationとDocs更新を含める。P1-5まで不整合な起動手順を放置しない。

BaselineのPythonコマンドは現行CIに合わせて `python -m unittest discover -s tests -p 'test_*.py'` を基本とし、pytest固有テストの有無を確認して統一する。Frontendは `npm run typecheck`、`npm test`、`npm run build`、`npm run test:a11y`、`npm run test:docs-a11y`、Docsは `npm run build` を記録対象とする。

既知失敗の記録はPhase 0の調査完了に必要だが、リリース許可を意味しない。後続Phaseのリリース前には全自動テスト・Buildを成功させる。

## 3. Phase 2 — 機能を変えず責務を分離する

1. **共通DB層を確立する。** P1のMigration実装を拡張し、Connection、Transaction、WAL、busy timeout、Backupを集約する。全RepositoryのコンストラクタDDLを明示CLIへ移し、未適用Schemaでは起動時に明確に失敗させる。
2. **RepositoryをDomainごとに分割する。** 設定・認証を扱うDashboardから開始し、Community、Engagement、Social、Moderationへ進む案とする。実際の順はV1削除後の依存表で確定する。既存Ticket / Reaction Roles / Suggestionsも共通接続を使い、Service内SQLをRepositoryへ移す。各移動で公開動作を維持する。
3. **非同期処理の共通契約を作る。** TicketとReaction RolesのLease・Retry差異を比較し、ProtocolとRunnerを抽出してからSocial・Moderationへ適用する。Domainテーブルの一括統合はしない。Lease失効・再取得、所有者以外の完了拒否、重複Event、Backoff、Dead Letter、Cancel、Retentionを共通テストで検証する。
4. **Discord操作をAdapterへ集約する。** ServiceはID・値・Domain Eventを受け取り状態遷移と冪等性を担当する。Retry可能・恒久失敗・競合・補償失敗を明示し、作成済みDiscord Resourceの孤立を記録・復旧できるようにする。
5. **APIをDomain Routerへ分割する。** OAuth、CSRF、Guild所属、Resource検証、revisionを共通Dependencyへ移す。現行応答のContract testを先に用意し、URLは維持する。エラー・Pagination・ID・日時の統一は呼出し側との対応を同一変更で行う。
6. **画面とSchemaを整理する。** OpenAPIからTypeScript型を生成し、入力制約も共通Schemaへ接続する。まずSave Bar・Resource Picker・Access Policy、次に既存実装からForm・Embed・Schedule・Permission Diagnosticsを抽出する。`App.tsx` はShellとRouterへ縮小し、Route単位で遅延読込、翻訳をNamespace化する。

完了判定は、新しい小規模なDomain変更が巨大ファイルへのSQL・Route・画面追記を必要としないこと。見た目の再設計は行わず、`design.md` と `tokens.css` を維持する。保存・再読込の往復、認可、409競合、無効化のContract testを必須とする。

## 4. Phase 3 — 同一Imageで運用する

| 作業単位 | 内容 | 検証 |
| --- | --- | --- |
| Image | Node stageでSPA / Docs、Python builderで依存を構築。Runtimeは非root・read-only・権限昇格禁止。 | 同じImageのCommandを切り替えてbot / dashboard / social-worker / migrate / testを起動できる。testの依存・資材の配置も明示する。 |
| Compose | 共通設定とdev / stage / prodの差分を分離。DevだけSource mount・Vite・reloadを使う。 | Token、OAuth callback、project名、Network、Volumeが環境間で混ざらない。Stage / 本番は同一digestを使用する。 |
| 永続化・起動 | `/var/lib/tueka` のnamed volumeへDB、WAL/SHM、Transcriptを集約。Migration成功後に3Serviceを起動。 | 空Volume導入と旧Versionからの更新を検証。SQLiteは単一Host、各Service単一Replicaで運用する。 |
| 監視・公開 | Dashboard liveness/readiness、Bot / Worker heartbeat、エラー率、Outbox最古滞留時間、SQLite lock待ちを観測。 | 異常を注入して検出可能か確認。初回はHostのNginx / TLSを維持し、Dashboardを127.0.0.1:8000だけに公開する。 |
| 復旧 | Backup / Restore one-shot service、固定digest、ログ制限、Resource上限、Backup jobを追加。 | 別Volumeへの復元と旧ImageへのRollbackを手順書だけで実行。Transcript復号と保留処理の再開も確認する。 |

PostgreSQL移行はこのPhaseの前提にしない。Stageでピーク相当の処理量を計測し、lock待ち・配送遅延・許容エラー率の閾値を運用要件から決めて記録する。閾値超過が継続し、Transaction短縮・Index・Batch調整で解消しない場合に移行案を評価する。

## 5. Phase 4 — 既存機能を管理画面から運用可能にする

最初に機能を「安定」「改善中」「利用不可」に分類する判定表を作り、Feature Registry・UI・Docsの表示を揃える。利用不可の設定は公開しない。実機検証前に「安定」と断定しない。

| 順序の目安 | 対象 | 一連の受入シナリオ |
| --- | --- | --- |
| 1 | Moderation | Rule preview→処置→Case確認→誤検知取消→監査突合。実行権限・Role階層不足から復旧できる。Appealの本格WorkflowはPhase 5で実装する。 |
| 2 | Ticket | 6タブ設定→Panel公開→受付→Claim→回答待ち→Close→Transcript→Feedback。部分失敗・再起動も検証する。 |
| 3 | Reaction Roles | 全Typeの公開・付与・解除・期限・Link・修復。Emoji消失とRole階層変更を診断する。 |
| 4 | Social | Target解決→Webhook / Poll→配送→Preview→失敗追跡→Retry。欠落補完と初回過去投稿抑止を確認する。 |
| 5 | Suggestions | 審査理由・状態履歴の閲覧、Discussion、実装済み通知、Dashboardからの管理を追加する。既存 `suggestion_events` を活用し重複した履歴保存を作らない。 |
| 横断 | 全画面 | Picker、空状態、権限不足、Resource消失、保存競合、部分失敗、復旧、Docs linkを共通化。日英・テーマ・キーボード・320/375/414/768pxを確認する。 |

不具合の実害が大きいものは上記順序より優先する。Suggestionsの基本的なDiscussion・通知はここで完成させ、Phase 5ではカテゴリ・タグ・重複統合・Kanbanへ拡張する。

## 6. Phase 5 — 共通基盤を使って縦に完成させる

ROADMAPの順序を維持する。各機能をDBだけ・画面だけで公開しない。

| 順序 | 機能 | 主な再利用基盤 |
| --- | --- | --- |
| 1 | Forms / Applications | Form、Access Policy、審査、Audit |
| 2 | Moderation Appeals / ModMail | Case / Infraction、Ticket、Form、審査 |
| 3 | Scheduled Messages / Events | Schedule、Embed、Outbox、Permission Diagnostics |
| 4 | Suggestions Roadmap | 既存提案・履歴・Discussion、カテゴリ、タグ、重複統合、Kanban |
| 5 | Starboard / Highlights | Event正規化、Outbox、編集・削除追従 |
| 6 | Giveaways / Community Events | Access Policy、期限処理、監査、再抽選 |
| 7 | Server Insights | 運用Metrics、Retention、集計。本文の長期保存に依存しない。 |

各公開単位にRegistry・権限、番号付きMigration、Repository、Service、Adapter / Cog、認可とrevision対応API、日英UI、モバイル、異常系・復旧、Unit / Integration / API / Frontend / Accessibility test、正式Docs、Retention・監査・Backup・無効化挙動を含める。

音楽、任意コードWorkflow、本文の外部AI分類、独自決済、実測根拠のないMicroservice / Redis / Kafka導入は対象外とする。

## 7. リリース判定・リスク・着手条件

- 各Phaseのリリースは全テスト・Build成功、空DB・直前Version・再適用のMigration検証を条件とする。破壊的Migrationでは途中失敗・Rollback・V2データ保持も検証する。
- StageでOAuth、Discord command、Webhook、Outbox、Scheduleを実動確認する。Frontendのmockやローカルテストだけで代替しない。
- Backupを別VolumeへRestoreし、DBとTranscript・鍵世代の整合を確認する。V1削除後は旧Imageへの切替だけで復旧できるとは限らない。必要なSnapshot復元と、Snapshot以後に失われるデータ範囲をリリースごとに明記する。
- README、環境変数、起動・更新・復旧Docsを実装と同期する。旧文書を消す前にリンクと内容の移管を確認する。
- SQLite競合、Outbox滞留、Worker停止、Discord側成功後のDB失敗を重点監視する。特にRetryは「最大回数」だけでなく冪等性と補償を検証する。
- 本番DB InventoryとStage検証には、運用環境・テストGuild・OAuth/Provider設定へのアクセスが必要。アクセスがない期間も、コードInventory、Fixture、コンテナ、Contract testの整備は進められる。

直近の着手はP0-1。次にP0-2、P0-3、P0-4を終えて削除範囲を確定する。納期はBaselineとInventoryから作業量を見積もって設定し、Phase 2以降の詳細チケットは前Phase終了時のコードを基準に更新する。
