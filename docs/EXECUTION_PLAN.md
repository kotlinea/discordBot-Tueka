# Tueka 実行計画

策定日：2026-09-10。方針と実施順序の正本は [ROADMAP.md](../ROADMAP.md)。本書は、その方針を現在のコードに対応付けた作業計画であり、新しい公開仕様ではない。

## 現在地と次の実行順序（2026-09-16確認）

初回調査表は策定時点の記録である。P0-1〜P1-5のローカル実装・検証、P2-1の共通DB層・明示Migrationへの統一を完了し、結果は `PROGRESS0910.md` に保存した。実Guild、遠隔本番DB、Stageのリリース判定は未完了であり、ローカル実装完了と区別する。

**P2-2：Domain別Repositoryの分離はローカル完了。** Dashboard認証・個人設定、Guild設定、Community、Engagement、Social、Moderationを専用Repositoryへ分離し、Cog / API / Workerが直接利用する。旧 `storage.py` と委譲窓口を除去した。Socialの実装は `social/`、従来のAutoModとModerationの実装は `moderation/` にまとめた。Ticket Service・Cogの直接SQLもRepositoryへ移した。Schemaと0001〜0007は変更していない。

Windows/Linuxの全Python各211件、Docs build、保全DB複製の全Dump不変・整合性成功・FK違反0を確認した。各Domainの詳細と一時不具合の修正は進捗記録を参照する。

**P2-3：Outbox / ScheduleのProtocol・Runner共通化はローカル完了。** `jobs/` に共通契約・保存処理・Runnerを配置し、Ticket / Reaction RolesのOutbox/Schedule、Socialイベント、Moderation要求/期限処理の7 Queueへ適用した。0008でToken・不足列・検索Indexを追加。取得ごとのToken・失効検査、最大8回のRetry、Dead Letter、30日Retention、Cancel・Lease更新を共通化した。既存DomainのPayloadとテーブルは維持する。

最終コード固定後のWindows/Linux各220件、Docs build、直前0007からのMigration回帰、保全DB既存64表の全列・行保持を確認した。P2-3時点の検証用複製は `data/backups/p2-jobs-0914/verified.sqlite3`。同ディレクトリのfinalは開発途中候補なので次の検証に使用しない。

**P2-4：Discord操作のAdapter集約はローカル完了。** Moderation、Ticket、Reaction Roles、Social、SuggestionsにService/Port/Discord Adapterの境界を設けた。CogのInteraction応答は入口に残し、外部Resourceの操作をAdapterへ集約した。単なる移設に留めず、以下を検証した。

1. ServiceのDiscord/FastAPI依存禁止、Cogの外部Discord操作委譲、SQLのRepository集約を構造テストで確認。`moderation/adapter.py` は将来のNative AutoMod同期契約として区別した。
2. Ticketの作成・Panel公開・返信・通知のIntent/Receipt、Claim補償、Reaction RolesのRole補償、Social/Suggestionsの不明配送照合を実装。Discord成功後DB失敗、権限喪失、補償競合、再起動で成功を誤記録しないことを確認した。
3. ProviderとPanelの所有権を検査し、Lockdown・Ticket Claim・Reaction Rolesの変更/復旧/期限処理に更新可能なResource Leaseを適用。Token・有効期限とDB確定を同じTransactionで検査する。Role補償では監査ログを照合し、人手変更と証拠不足を保留する。
4. 0009でSuggestionsを8番目の共通Queueへ追加、0010でResource Lease表を追加。0001〜0008は変更していない。0009/0010も保全DBへ検証済みのため、以後のSchema追加は0011から行う。
5. 固定コードのWindows/Linux各272件、正式Docs build、0008からの実Schema更新・保持・再適用、保全複製の既存66表98行の保持を確認した。最新の検証用複製は `data/backups/p2-adapters-0916/verified.sqlite3`。詳細な結果とログは `PROGRESS0910.md` を参照する。

次の開発単位は **P2-5：Domain API Routerと共通Dependencyへの分割**。先に現行 `/api/v1` のURL・応答・認可・CSRF・Guild/Resource境界・revision競合のContract testを固定し、Domain単位でRouterを移す。OAuth/Session・Guild所属・Resource検証・競合応答を共通Dependencyへ整理し、API名のV1を旧Dashboard V1と混同しない。P2-5の検証・Docs完了後にP2-6の型生成とUI構造へ進む。

原DB・既存保全DBは変更していない。StageのDiscord・OAuth・Webhook実動、遠隔本番DB適用、実S3復元の未検証をローカル成功で代替しない。Phase 2全体とGoalは継続する。

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

直近の着手はP2-5。P0-1〜P2-4のローカル完了済み作業をやり直さず、既存の検証基盤と保全Fixtureを利用する。納期は担当者・Stage環境の可用性と各単位の見積りから設定する。

## 8. 再調査に基づく具体的な実行単位（2026-09-12）

今回の更新は計画策定のみ。README、ROADMAP、Architecture、進捗、Migration一覧、Bot / Worker起動処理、保存層、Repository、Service、API、Frontendの実行コマンドとCIを静的に照合した。186件のPython成功などは `PROGRESS0910.md` の既存記録であり、今回再実行した結果ではない。調査開始時の作業ツリーはクリーンだった。

### P1-5の実施・検証範囲（ローカル完了）

1. **削除範囲を確定する。** `migrate_json.py`、`GuildStorage.migrated` / `migrate_json`、`json_migration_v1` の参照と入力JSONの必要性をInventoryで確認する。ローカル調査で遠隔本番の状況を断定しない。
2. **現行設定を保全する。** `storage.py` のWelcome / Leveling / Autorole / Audit設定は現在も共有設定や旧形式を参照する。読書き箇所と有効値を一覧化し、必要な値を番号付きMigrationで固定してからRuntimeの互換分岐を削除する。共有テーブル全体を名前だけで削除しない。Social初期化時のデータ補完も、V1移行か現行V2の修復かを分類する。
3. **初期化手順を成立させる。** JSON CLIが現在担うDB初期化の代替を整えてから削除する。全RepositoryのDDL移設はP2-1で行うが、P1-5終了時点でも空DBから正式手順だけで起動できることを必須とする。
4. **正式Docsへ統合する。** README、日英Getting Started、Linux、Upgrade、Backupを番号付きCLIへ統一する。`PROGRESS0814.md`、`DEPLOYMENT_TODO.md`、`FEATURE_MODULE_GUIDE.md`、`TICKETS_V2.md` は必要事項の移管後に削除し、VitePress設定とリンクを点検する。現在の進捗記録 `PROGRESS0910.md` は保持する。
5. **Phase 1の出口を検証する。** 空DB・直前版・V2専用・混在Fixtureで保持データ、再適用、途中失敗Rollbackを検証する。Bot / Dashboard / Workerの再初期化後にも旧Schemaが復活しないこと、全Python・Frontend・Docs・Accessibility検証の成功を記録する。実Discord・OAuth・WebhookはStageで別途確認する。

### P1-5以降の作業分割

各行を一つのレビュー単位の目安とする。大きい行はDomainごとに分割し、途中でも起動可能な状態を保つ。

| ID | 具体的な変更 | 前提・受入条件 |
| --- | --- | --- |
| P2-1 | 共通DB接続と明示Migrationへ統一。`storage.py` とTicket / Reaction Roles / SuggestionsのコンストラクタDDLを移設する。 | P1-5。空DB初期化・既存更新・未適用時の明確な起動失敗・接続設定の一致。 |
| P2-2 | Dashboard設定/認証→Community→Engagement→Social→Moderationの順でSQLをRepositoryへ移す。Ticket Serviceの直接SQLも移す。 | P2-1。移動前後の契約テストと保存・再読込が一致。順序は依存表で最終確認する。 |
| P2-3 | Ticket / Reaction Rolesの実装を比較し、Outbox / ScheduleのProtocol・Runnerを抽出、Social / Moderationへ適用する。 | P2-2の対象Domain。Lease所有権、失効、再試行、重複、Dead Letter、保持期限を共通テストで保証。 |
| P2-4 | ServiceのDiscord操作をAdapterへ移し、失敗分類と補償・孤立Resourceの復旧を統一する。 | 対象Repositoryの分離。Discord成功後DB失敗、権限喪失、再起動の異常系を検証。 |
| P2-5 | `dashboard/api_v1.py` をDomain Routerへ分割し、認証・CSRF・Guild認可・revisionを共通化する。 | 応答Contract testを先に追加。現行 `/api/v1` URLと認可境界を維持。 |
| P2-6 | OpenAPI型生成、入力制約の共有、共通UI抽出、`App.tsx` 分割、Route遅延読込み、翻訳Namespace分割。 | P2-5。型生成の差分検査、保存往復、競合・権限・4画面幅・日英・テーマ・キーボード操作を検証。 |
| P3-1 | SPA / Docsを含む本番Imageとコマンド別entrypointを作る。 | Phase 2出口。非root・read-onlyでBot / Dashboard / Worker / Migrationが起動する。 |
| P3-2 | dev / stage / prodのCompose、永続Volume、Migration後の起動順、秘密情報の注入を整える。 | P3-1。空Volume導入・更新・環境分離・Stageと本番の同一digestを確認。 |
| P3-3 | Readiness、Heartbeat、Outbox滞留・SQLite競合の監視、ログ/Resource制限を追加する。 | P3-2。Worker停止や配送失敗を注入し検出可能。閾値はStage実測から決める。 |
| P3-4 | Backup / Restoreコマンドと運用手順を完成させる。 | P3-2。別Volume復元、Transcript復号、保留処理再開、Snapshotを伴うRollbackを実演。 |
| P4-1 | 全機能の実装・テスト・実機検証を対応付け、安定/改善中/利用不可をRegistry・UI・Docsへ反映する。 | Phase 3出口。未検証の機能を安定と表示しない。 |
| P4-2〜6 | Moderation→Ticket→Reaction Roles→Social→Suggestionsを第5節のシナリオで完成させる。 | P4-1。各機能の正常系・部分失敗・復旧までDashboardから運用可能。 |
| P4-7 | 全画面の空状態・権限不足・競合・復旧・Docs案内と日英/モバイル操作を最終確認する。 | P4-2〜6。横断検証とStage受入の記録が揃う。 |
| P5-1〜7 | 第6節の7機能を記載順に、一機能ずつDBからBot・API・UI・運用まで完成させる。 | Phase 4出口。共通基盤を再利用し、各機能のMigration・権限・無効化・Retention・復旧・Docsを含めて受入する。 |

実装担当は変更・テスト・Docs、レビュー担当はデータ保持と公開契約、運用担当はStage・Backup復元を確認する。担当者名は未定。各単位の着手時に担当・見積り・依存を確定し、完了時にコマンド、結果、未検証事項、次の着手点を進捗へ残す。外部環境が未準備でもローカルの設計・検証整備は進められるが、リリース判定は第7節の条件を満たすまで保留する。
