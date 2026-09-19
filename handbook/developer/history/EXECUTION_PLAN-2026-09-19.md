> 履歴資料です。現在の優先順位・状態は[現行計画](../EXECUTION_PLAN.md)を参照してください。

# Tueka 実行計画

策定日：2026-09-10。方針と実施順序の正本は [ROADMAP.md](../../../ROADMAP.md)。本書は、その方針を現在のコードに対応付けた作業計画であり、新しい公開仕様ではない。

## 現在地と次の実行順序（2026-09-19確認）

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

**P2-5：Domain API Routerと共通Dependencyへの分割はローカル完了。** `dashboard/api_v1.py` はContext生成と9 Routerの合成だけを担当し、DomainのHTTP処理は `dashboard/api/` に配置した。OAuth/Session・CSRF・Guild認可・Ticket担当Team・Resource Index・revision競合を共通化。分割前のOpenAPI 59パスと認証/認可/CSRF 199ケースを固定して互換性を検証した。Guildを退出した明示Teamメンバーを拒否し、不正なrevision Headerは422で返す。Windows/Linux全各288件、Frontend型検査、正式Docs build（11.22秒）が成功。詳細は進捗記録を参照する。

**P2-6：型生成・入力Schema共有・UI構造の整理はローカル完了。** Domain別公開Schemaと共通入力検証、OpenAPI/TypeScript/制約生成、共通UI、Shell/Domain Router、画面遅延読込、日英Namespaceを実装した。最終Windows/Linux全各296件、Frontend型検査/build、Vitest14件、4画面幅の画面検証48件、Docs表示/Accessibility10件が成功。イベントのnullable項目と19桁ID、保存・再読込・競合・権限喪失・無効化、Embed/Schedule編集、日英・全外観/light/dark・キーボードを検証した。詳細とログは進捗記録を参照する。

**P2-7：PostgreSQL移行はローカル完了（2026-09-19）。** 接続/Pool・専用Migration・9 Domain Repository・Queue/Lease・API競合・Runtime・型生成・テスト/CI設定・論理Backup/RestoreをPostgreSQLへ統一した。最終Windows/Linux各298件、Frontend単体14件・本番build、画面回帰48件、Docs build・5画面幅10件、型生成差分検査が成功。実pg_dump/pg_restoreで67テーブル、設定・Queue・Transcript参照、採番と破損dumpのRollbackを確認した。

開発用Composeを空Volumeから起動し、localhost:55433の`tueka_dev`へ初期Migrationを適用した。アプリの`.env`もDATABASE_URLへ切替済み。元SQLite・保全DB・暗号鍵・Transcript・Discord Resourceは変更せず、データは移送していない。Bot・Dashboard・Workerの外部接続は起動していない。

**P3-1：同一の本番Imageとコマンド別entrypointはローカル完了。** NodeでSPA/Docs、Python builderでhash付きLock依存を構築し、非rootの同じImageでbot/dashboard/social-worker/migrate/testを実行する。read-only・権限昇格禁止・Capability除去でPython全302件、空SchemaのMigration/再適用、実HTTPでのSPA/Docs/assets配信、Worker Heartbeat、正常終了を検証した。Botの全Cog起動/再起動はオフライン回帰で確認。PID 1のSIGTERM問題を共通Lifecycleで修正した。

**P3-2：環境別Compose・Volume・秘密情報・起動順はローカル完了。** 共通Composeとdev/stage/prod差分、環境別設定の生成・検査、停止→DB readiness→Migration成功→3Service起動を実装した。隔離した3 Projectで空Volume、DB/Transcript保持、Schema更新/失敗Rollback、環境分離、Stage/本番の同一Image ID、DevのVite/API proxy/実Source reloadを確認。最終Windows/Linux各315件、Frontend単体14件・画面48件とImage内の実配信/正常終了が成功した。

**P3-3：Readiness・Heartbeat・DB/Queue監視・ログ/Resource制限はローカル完了。** `observability/`に観測処理をまとめ、HTTP health、認証付きメトリクス、3ServiceのHeartbeat、Pool/lock/deadlock、8 Queue、JSONログとCompose上限を実装した。Windows/Linux各328件、隔離ComposeのWorker停止・配送失敗・DB停止/復旧、68表の論理Restoreが成功。開発DBもBackup後に0002を適用済み。

**P3-4：Backup/RestoreとRollbackはローカル完了。** 環境別one-shot、対応Image/鍵世代/DB/暗号化Blobの復旧セット、別Project/Volume復元、起動保留/解放/中止、排他、定期Backup Jobテンプレートを追加した。破損dumpのRollbackと復旧中止、Transcript/添付/DB暗号文の復号、Receiptを照合する保留配送、実際に異なる新旧Image/Schemaへの更新とRollbackを隔離Composeで実演した。

**次はPhase 3の実Stage受入。** ユーザーは2026-09-19にStage/Guild/Registry/Host未準備と回答し、ローカル検証と実機受入手順の整備まで進める方針を指定した。`docs/operations/stage-acceptance.md`へ必要な対象・手順・証拠をまとめた。Stage実測の閾値、Discord/OAuth/Webhook、Registry経由の同一digest配布、実Transcript/S3、Host転送先と定期Job/通知の確認を未完了として残す。P4-1の前提であるPhase 3の運用出口はまだ満たしておらず、Phase 4〜5へ進んだとは扱わない。Remote Workflowも未実行。詳細は`PROGRESS0910.md`のP3-4記録を参照する。

## 1. 判断と調査範囲

Phase 0〜2とP3-1〜4のローカル実装・検証を完了した。直近はStageの準備後に実運用出口を確認し、P4-1の機能判定表へ進む。既存機能の運用品質を満たしてからPhase 5へ進む。

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

7. **PostgreSQLへ移行する。** P2-6の公開契約と責務分離を維持し、全Repository・Queue/Lease・Migration・起動設定・テスト基盤をPostgreSQLへ移す。原開発DBのデータ移送は不要。具体的な実行順と受入条件は第9節に定める。

完了判定は、新しい小規模なDomain変更が巨大ファイルへのSQL・Route・画面追記を必要としないこと。見た目の再設計は行わず、`design.md` と `tokens.css` を維持する。保存・再読込の往復、認可、409競合、無効化のContract testを必須とする。P2-7後は実PostgreSQLの空DB・同時更新・Migration・Queue/Lease回帰をPhase 2の出口に追加する。

## 4. Phase 3 — 同一Imageで運用する

| 作業単位 | 内容 | 検証 |
| --- | --- | --- |
| Image | Node stageでSPA / Docs、Python builderで依存を構築。Runtimeは非root・read-only・権限昇格禁止。 | 同じImageのCommandを切り替えてbot / dashboard / social-worker / migrate / testを起動できる。testの依存・資材の配置も明示する。 |
| Compose | 共通設定とdev / stage / prodの差分を分離。DevだけSource mount・Vite・reloadを使う。 | Token、OAuth callback、project名、Network、Volumeが環境間で混ざらない。Stage / 本番は同一digestを使用する。 |
| 永続化・起動 | PostgreSQL Serviceのnamed volumeとアプリのTranscript volumeを分離。DB readiness→Migration成功→3Service起動の順にする。 | 空Volume導入とPostgreSQL Schema更新を検証。アプリは当初各Service単一Replica、DBポートは内部Networkに限定。 |
| 監視・公開 | Dashboard liveness/readiness、Bot / Worker heartbeat、エラー率、Outbox最古滞留時間、PostgreSQLの接続待ち・lock待ち・deadlockを観測。 | 異常を注入して検出可能か確認。初回はHostのNginx / TLSを維持し、Dashboardを127.0.0.1:8000だけに公開する。 |
| 復旧 | Backup / Restore one-shot service、固定digest、ログ制限、Resource上限、Backup jobを追加。 | 別Volumeへの復元と旧ImageへのRollbackを手順書だけで実行。Transcript復号と保留処理の再開も確認する。 |

P2-7のPostgreSQL移行完了をこのPhaseの前提とする。Stageでは接続Pool待ち、Transaction/lock時間、deadlock、配送遅延、エラー率を計測し、運用閾値を決める。DB移行の着手可否ではなく、容量・Index・Transaction・Pool設定の調整に測定結果を使う。

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

- 各Phaseのリリースは全テスト・Build成功、空DB・直前Version・再適用のMigration検証を条件とする。破壊的Migrationでは途中失敗・Rollback・必要なデータ保持も検証する。今回の原開発DBは破棄可能という例外を明記し、PostgreSQL導入後のStage/本番データへこの例外を拡張しない。
- StageでOAuth、Discord command、Webhook、Outbox、Scheduleを実動確認する。Frontendのmockやローカルテストだけで代替しない。
- Backupを別VolumeへRestoreし、DBとTranscript・鍵世代の整合を確認する。V1削除後は旧Imageへの切替だけで復旧できるとは限らない。必要なSnapshot復元と、Snapshot以後に失われるデータ範囲をリリースごとに明記する。
- README、環境変数、起動・更新・復旧Docsを実装と同期する。旧文書を消す前にリンクと内容の移管を確認する。
- PostgreSQLの接続枯渇・lock競合・deadlock、Outbox滞留、Worker停止、Discord側成功後のDB失敗を重点監視する。特にRetryは「最大回数」だけでなく冪等性と補償を検証する。
- Stage検証と将来の本番PostgreSQL運用確認には、対象環境・テストGuild・OAuth/Provider設定へのアクセスが必要。原開発DBのInventory/移送はP2-7の着手条件にしない。アクセスがない期間も、コードInventory、Fixture、コンテナ、Contract testの整備は進められる。

直近の着手はP3-3。P0-1〜P3-2のローカル完了済み作業をやり直さず、既存の検証基盤と保全Fixtureを利用する。納期は担当者・Stage環境の可用性と各単位の見積りから設定する。

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
| P2-7 | PostgreSQL用Schema・接続・全Repository・Queue/Lease・起動設定・テスト/型生成基盤を移行する。 | P2-6。空の実PostgreSQLで全回帰・同時更新・Migration・Backup/Restoreが成功。原開発DBの移送は不要。 |
| P3-1 | SPA / Docsを含む本番Imageとコマンド別entrypointを作る。 | Phase 2出口。非root・read-onlyでBot / Dashboard / Worker / Migrationが起動する。 |
| P3-2 | dev / stage / prodのCompose、永続Volume、Migration後の起動順、秘密情報の注入を整える。 | P3-1。空Volume導入・更新・環境分離・Stageと本番の同一digestを確認。 |
| P3-3 | Readiness、Heartbeat、Outbox滞留・PostgreSQL接続/lock競合の監視、ログ/Resource制限を追加する。 | P3-2。Worker停止や配送失敗を注入し検出可能。閾値はStage実測から決める。 |
| P3-4 | Backup / Restoreコマンドと運用手順を完成させる。 | P3-2。別Volume復元、Transcript復号、保留処理再開、Snapshotを伴うRollbackを実演。 |
| P4-1 | 全機能の実装・テスト・実機検証を対応付け、安定/改善中/利用不可をRegistry・UI・Docsへ反映する。 | Phase 3出口。未検証の機能を安定と表示しない。 |
| P4-2〜6 | Moderation→Ticket→Reaction Roles→Social→Suggestionsを第5節のシナリオで完成させる。 | P4-1。各機能の正常系・部分失敗・復旧までDashboardから運用可能。 |
| P4-7 | 全画面の空状態・権限不足・競合・復旧・Docs案内と日英/モバイル操作を最終確認する。 | P4-2〜6。横断検証とStage受入の記録が揃う。 |
| P5-1〜7 | 第6節の7機能を記載順に、一機能ずつDBからBot・API・UI・運用まで完成させる。 | Phase 4出口。共通基盤を再利用し、各機能のMigration・権限・無効化・Retention・復旧・Docsを含めて受入する。 |

実装担当は変更・テスト・Docs、レビュー担当はデータ保持と公開契約、運用担当はStage・Backup復元を確認する。担当者名は未定。各単位の着手時に担当・見積り・依存を確定し、完了時にコマンド、結果、未検証事項、次の着手点を進捗へ残す。外部環境が未準備でもローカルの設計・検証整備は進められるが、リリース判定は第7節の条件を満たすまで保留する。


## 9. P2-7 PostgreSQL移行の実行計画（2026-09-18追加）

目的は保存先のPostgreSQL一本化であり、公開機能の再設計や既存開発データの救済は含めない。P2-6の完了を前提とする一つの作業単位として、以下の順に実装・検証・Docs更新まで完遂する。

1. **境界とテスト基盤を固定する。** `database.py`、`migrate.py`、全Domainのrepository、`jobs/repository.py`、`jobs/leases.py`、起動設定、DB Inventory/型生成/テストFixtureを棚卸しする。SQLite固有のプレースホルダー、PRAGMA、INSERT OR IGNORE/REPLACE、lastrowid、JSON・集計・採番・rowcountの依存を分類する。専用PostgreSQLコンテナと隔離テストDBを用意し、Python 3.13用Driver/PoolとDB ImageをLockする。テストは稼働中アプリDBを再利用しない。
2. **接続とMigrationを作る。** `DATABASE_URL`を入口に、Connection/Pool・Transaction・例外分類・Schema適用済み検査を共通化する。現行V2 SchemaからPostgreSQL専用の初期Migrationを作り、別の履歴として管理する（例：`migrations/postgresql/0001_initial.sql`）。SQLite 0001〜0010は過去の履歴として保持し、PostgreSQLへ流用しない。空DB、再適用、Checksum不一致、途中失敗Rollback、同時Migration拒否を検証する。
3. **RepositoryをDomain順に切り替える。** Dashboard/Guild設定→Community/Engagement→Social/Moderation→Ticket/Reaction Roles/Suggestions→共通Jobsの順に移す。内部ID採番、Discord IDの容量、JSON、bool、UTC時刻、外部キー、Unique/Index、UPSERTとRETURNINGを明示する。公開ID/日時/エラー契約はP2-6のまま維持する。単なるSQL文字列置換で済ませず、Repositoryの保存・更新・削除・revision競合を実PostgreSQLで確認する。
4. **並行処理と失敗時の契約を確認する。** Outbox/Scheduleの取得をTransactionと行ロックで実装し、複数取得者の重複Claim、Lease更新/失効/旧所有者ACK、Resource Lease、Cancel/Dead Letter/Retentionを実DBで検証する。DB時刻・Transaction境界を明確化し、deadlock/接続断/タイムアウトの再試行はDB処理の冪等性を確認する。Discord副作用を含む処理全体の無条件再実行はしない。APIの同時revision更新も競合テストする。
5. **Runtime・開発コマンド・CIを一本化する。** Bot/Dashboard/Worker/Migration/型生成を同じ接続契約へ揃える。SQLiteのRuntime fallback、不要なDBファイル設定/Backup処理を除去し、全テストFixtureを専用PostgreSQLへ変更する。WindowsクライアントとLinuxコンテナの両方から実PostgreSQLに対してテストする。型生成の一時DB/schemaにも隔離と確実な後始末を設け、秘密値を生成物へ含めない。
6. **開発DBを切り替え、復旧手順を検証する。** 原DBは破棄・再作成可能なのでETL・Dual Write・旧SQLiteへの新データ逆移送を作らない。対象の開発接続先/Volumeを明示した初期化手順を用意する。DBの再作成とDiscord上の既存Panel/Role/Channelの扱いを分離し、孤立Resourceを誤って再操作しないことを確認する。新しいPostgreSQLのBackupを別DBへRestoreし、設定・Queue・Transcript参照の復元を検証する。暗号鍵とTranscript/S3オブジェクトはDBリセットとは別管理とする。
7. **出口を判定する。** 空PostgreSQLから全起動入口が成立し、全Repository/API/Service/Queue回帰、型生成差分、Frontend/Docs build、画面回帰が成功していること。SQLiteがRuntimeに必要ないこと、データ未移送が意図した動作であること、開発DB再初期化・接続設定・Migration・Backup/Restoreを正式Docsへ反映したことを記録する。Stageの実Discord/OAuth/Webhookは別ゲートとして残す。

P3-1はこの接続/Migration契約を本番Imageへ載せ、P3-2で環境別PostgreSQL Service・Volume・秘密情報・起動順を構成する。P3-3の監視対象はSQLiteのWAL/lockではなくPostgreSQLの接続/Transaction/lock/deadlockとQueue指標へ変更する。P3-4ではDB論理BackupとTranscript・鍵を組み合わせた運用Restore/Rollbackを完成させる。
