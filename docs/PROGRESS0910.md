# 作業記録 2026-09-10

- 正本：`ROADMAP.md`。実行順序：`docs/EXECUTION_PLAN.md`。
- 全体状態：Phase 0 / P0-1を実施中。Phase完了・リリース可能とは判定していない。
- 記録方法：完了した作業、検証結果、決定事項、未検証事項と次の作業を追記する。過去の結果を後日の成功で書き換えない。

## P0-1 — Suggestions Domainの確認・競合修正

- 開始時の作業ツリーには未追跡の `docs/EXECUTION_PLAN.md` のみが存在した。既存Suggestionsの未コミット差分はなかった。
- Repository、Service、Cogと既存Domainテストを読み取った。
- 修正前の既存Domainテスト6件がPython 3.12.14で成功した。
- 投票処理は状態のSELECT後に書込みTransactionが開始される実装だった。審査完了との競合を防ぐため、`SuggestionRepository.vote` の状態確認前に `BEGIN IMMEDIATE` を追加した。
- 別接続から審査状態を書き換える回帰テストを追加し、投票の状態確認中に書込みロックが保持されること、審査完了後の投票が拒否されることを確認した。
- 別Guildからの読取り・投票・審査・メッセージ紐付け拒否、配送失敗の永続化と操作拒否、Repository再生成後のメッセージID・投票保持をテストへ追加した。
- 最初の追加テスト実行はSQLite接続の閉じ忘れによるWindowsの一時DB削除エラー1件で失敗した。テスト接続を `contextlib.closing` で閉じるよう修正した。
- 修正後：`python -m unittest discover -s tests -p test_suggestions.py -v` 相当をバンドルPythonで実行し10件成功、0失敗、0エラー、0.720秒。
- 実行Python：`C:\Users\shogo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`（3.12.14）。Python 3.13 Baselineの代替とは扱わない。
- 環境確認：PATH上の `python` / `py` は解決不可。Nodeはv24.12.0。Docker CLIは29.7.2だが `docker_engine` named pipeが存在せずEngineへ接続不可。Docker設定ファイルにもアクセス拒否が表示された。
- P0-1の残作業：Cogの権限・無効化・初回配送失敗・再起動後ボタン、APIのGuild/CSRF/revision、画面の日英と保存往復を検証し必要な修正を行う。Repository再生成テストをDiscordボタン実動検証とは扱わない。
- 次の着手：SuggestionsのCog/APIテスト環境の依存確認と異常系テスト追加。その後P0-2へ進む。V1削除はP0-3/P0-4完了前に開始しない。

## P0-1 — 画面の異常系・保存・翻訳

- 前回の継続は実装修正とテスト追加を伴う進捗として確認した。今回もP0-1を継続し、Phase完了とは判定していない。
- Suggestions設定の初回取得が失敗した際、draft未生成のLoading判定がエラー判定に先行していた。エラーを表示する順序へ修正した。
- 保存バーをフォームのsubmitへ接続し、フォーム内保存と同じHTML入力検証を通すよう修正した。
- 投稿先未設定時の保存禁止を「有効化する場合」に限定し、無効化の保存を可能にした。
- 項目移動・削除、追加項目の初期ラベル、未保存領域のアクセシブル名を日英辞書へ接続した。固定の「1件」表示を削除した。
- React Testing Libraryによる4件の回帰テストを追加。初回取得失敗、日英それぞれの項目操作表示、投稿先なしの無効化保存とサーバー応答revisionの反映を確認した。
- テスト整備中の失敗：jsdomにResizeObserverがないためスタブを追加、翻訳辞書のラッパー重複とテストのラベル照合を修正した。最後の実行は4件成功、テスト526ms、全体2.69秒。
- API呼出しは画面テストではmock。実APIの認可・CSRF・revision競合や再読込を検証したとは扱わない。HTML入力検証のブラウザ実動確認も残る。
- 専用 `.venv-p0` を作成。通常実行のpipはネットワーク制限で失敗したが、承認済み権限で `pip install -r requirements.txt` が成功した。discord.py 2.7.1、FastAPI 0.141.1等がインストールされた。Pythonは引き続き3.12.14でありLock/Baselineではない。
- 型検査は最初にルートディレクトリで実行してpackage.json不在で失敗。Frontendでの実行時には既存tsbuildinfoへの書込み拒否と修正途中の重複JSX属性を検出した。属性修正後、承認済み権限で型検査を実行した。
- 次の作業：専用venvを使ってCog/APIテストを追加・実行し、画面の競合・下書き保持とブラウザ操作を検証する。P0-2以降は未着手。

## P0-1 — API・Cogの統合テスト

- 前回の画面修正とテストの差分が作業ツリーに残っていることを再確認し、P0-1を継続した。
- 実APIの保存処理は無効状態でも投稿先とBot権限を必須としていた。画面の無効化保存と一致するよう、未設定チャンネルと権限不足を無効状態では許容した。指定された別Guild Resourceの拒否は維持した。
- Suggestions保存APIでrevision省略を422として拒否した。競合時は409で、保存済みの設定が変化しないことを検証した。
- 共通CSRF検証でヘッダーとセッション値が双方空の場合に一致と扱われていた。空値を明示的に拒否するよう修正した。
- `tests/test_suggestions_api.py` を追加。実Router・実SQLiteに対して保存/GET一致、競合、revision必須、CSRF、認証、Guild認可、Resource検証、無効状態保存を検証。Discord APIのみAsyncMockを使用した。
- `tests/test_suggestions_cog.py` を追加。投稿成功・Discord Forbidden時の配送失敗、無効化、審査Role/Manage Messages、別Guild/メッセージ拒否、Cog再生成後の既存ボタン処理を検証。Discord通信はmockでありStage実動確認ではない。
- `.venv-p0/Scripts/python.exe -m unittest discover -s tests -p 'test_suggestions*.py' -v` は21件成功、4.672秒。Python 3.12.14。
- 共有CSRF修正の回帰確認として全Pythonテストを実行。152件、39.677秒、失敗1件。失敗は `test_docs.DocumentationTests.test_every_example_environment_variable_is_documented` で、`.env.example` の `BOT_INVITE_URL` が正式環境変数Docsにないという内容。他151件は成功。これはP0-3のコンテナBaselineではない。
- 全テストログはローカル `.venv-p0/python-tests.log`。非追跡の検証資材であり、この記録に件数・失敗理由を保存した。
- 依存からStarletteのTestClient/httpx非推奨警告が出た。今回のテスト失敗原因ではない。Lock確定時に互換性を検討する。
- P0-1の残作業：画面の保存競合・再取得による下書き消失の検証、実ブラウザで保存バーの入力検証と表示確認。全テストで判明した環境変数Docs不一致も修正が必要。P0-1完了・後続Phase開始とは判定していない。

## P0-1 — ローカル受入検証完了

- 再取得のたびに設定をdraftへコピーする実装を修正。未編集の場合は新しい設定を反映し、編集中は入力と元revisionを保持する。Guild変更時は前Guildの下書きを引き継がない。
- 回帰テストで背景更新後の下書き保持、保存失敗後の入力保持、元revision送信、破棄後の最新設定反映を検証。SuggestionsのVitestは5件成功、570ms（実行全体2.80秒）。
- 初回の追加テストは「Ideas」が入力とselect双方に一致して失敗。textboxのアクセシブル名で指定して修正した。
- Playwrightへ保存バーの必須入力検証、保存後の再読込、横overflow、axe serious/critical検査を追加した。HTTP APIはmockであり実APIとの接続検証ではない。
- 最初のブラウザ実行はtablet/desktop成功、320/375pxで共通Docsリンクのアクセシブル名不足が検出された。モバイルCSSで文字が隠れるため `DocsLink` に `aria-label` を追加した。
- 再実行は320/375/768/1440pxの4件成功、14.4秒。型検査も成功した。
- 環境変数Docsに `BOT_INVITE_URL` は現行Runtimeで未使用であると記載。Docsテスト6件成功、0.218秒。前回全体テストの唯一の失敗を対象テストで解消した。全体152件の再実行はまだ行っていない。
- 判定：P0-1の現行Suggestions範囲のローカル受入確認を完了。Domain/API/Cog/画面/ブラウザの証拠は上記各記録。実Discord・Stage、Python 3.13コンテナ、全Buildの成功を意味しない。これらは後続Baseline・リリース判定で実施する。

## P0-2 — テストコンテナ着手

- `Dockerfile.test` を追加。Python 3.13 slim上で依存をインストールし、unittestを実行する最小構成。
- `.dockerignore` に秘密値、仮想環境、依存ディレクトリ、DB/WAL/SHM、Transcript、Backup、テスト生成物を除外する規則を追加した。
- 現時点のDockerfileは既存requirements範囲指定によるbootstrap。Lockへ置換しクリーンbuildを実行するまではP0-2完了としない。
- 次の作業：Docker Engine接続とPython 3.13の利用方法を確認し、Python Lock生成・クリーンinstall、既存npm Lockの `npm ci` を検証する。P0-3/P0-4完了前のV1削除は行わない。

## P0-2 — 依存固定・クリーンinstall完了

- 前回は画面修正・検証とDockerfile追加を伴う進捗。今回の開始時に作業ツリーを再確認した。
- 承認済み権限でDockerを再確認し、desktop-linux Context、Docker Desktop 4.89.0、Engine 29.7.2、Linux amd64へ接続できた。前回のEngine未接続状態は解消している。
- Python 3.13コンテナでuv 0.8.22を使い、`uv pip compile requirements.txt --python-version 3.13 --universal --generate-hashes --output-file requirements.lock` を実行。62パッケージを解決しハッシュ付きLockを生成した。
- `Dockerfile.test` をPython Base Image digest `sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285` に固定。インストールを `pip install --require-hashes -r requirements.lock` と `pip check` へ変更した。
- `docker build --no-cache -f Dockerfile.test -t tueka-test:p0 .` は成功。build context 2.00MB。`pip check` は `No broken requirements found.`。
- 生成Image manifest list digest：`sha256:50912988627e78f29e81665d05fa41c2142c3eb7b0995b289ed1960b33633375`。実行Pythonは3.13.15。
- Frontendの `npm ci --no-audit --no-fund` は209パッケージ・20秒で成功。Docsは129パッケージ・15秒で成功。既存package-lockは変更していない。
- Docs installにはesbuild 0.21.5のinstall-scripts未承認警告があった。install終了コードは0だが、Docs buildで動作検証するまで警告を無視した成功判断に広げない。
- SHA256：requirements.lock=`0F1DD19D69DFDEC95C9BB1CE7BAE015AD7B370E12AAFB3F9272DED707DC57E95`、Frontend Lock=`D1EFB43D497E6DEEB9752E0C8FFAFDE392ABCBB38EFD43846D9F6D7E5FA4691C`、Docs Lock=`DCFB9587628CC0899BA1135E49EFC9AE31719D6BE7A11DEAD29729E94784230B`。
- `docs/TESTING.md` に固定依存での実行・更新手順を追加した。
- 判定：P0-2完了。universal Lock生成をWindows実行成功とは扱わず、Windows smokeはP0-3で整備する。

## P0-3 — PythonコンテナBaseline

- `docker run --rm --network none tueka-test:p0` は152テスト成功、29.267秒。Python 3.13.15 / Linux amd64。ネットワークを無効化し、本番Token・DBを渡していない。
- 元Commitは `e6706f181a6db70074549f7027be2d3d756f63a8`。実行対象には本作業の未コミット差分を含むため、そのCommit単体の成功記録ではない。Image digestを上記に記録した。
- buildログ：`.venv-p0/docker-build.log`。テストログ：`.venv-p0/docker-python-tests.log`。ローカル検証資材として非追跡。
- 未完了：Frontend型検査/Vitest/build、Docs build、両PlaywrightのコンテナBaseline、CIのLock利用・Windows smoke・container build・秘密情報検査。P0-3全体は継続中。
- 次はWeb用テストコンテナを整え、上記検証の件数と所要時間を記録する。P0-4のDB Inventory・Backup完了前にV1削除へ進まない。

## P0-3 — Web Baseline初回・Windows・CI整備

- 作業ツリーと前記記録を再確認。前回はLock生成・コンテナ検証を伴う進捗。P0-3の未完了項目を続行した。
- `Dockerfile.web-test` を追加。Node 24 bookworm-slimのdigestを `sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553` に固定し、npm Lockで依存を導入、Playwright ChromiumとOS依存をImageへ含めた。
- `scripts/web-baseline.mjs` を追加。6検査を順番に実行し、各ログ・終了コード・所要時間・Node版を保存する。途中失敗後も後続検査を取得し、いずれか失敗なら終了コード1とする。
- 初回Webコンテナ結果：型検査成功6.941秒、Vitest 10件成功2.724秒、Frontend build成功10.679秒、Docs build失敗1.467秒、Dashboard Playwright 24成功/4失敗66.775秒、Docs Playwright失敗2.416秒。
- 初回ログは `.venv-p0/web-baseline-first/`。停止済みコンテナ名は `tueka-web-baseline-0910`。初回結果を修正後の成功で書き換えない。
- Docs失敗はVitePressの `spawn git ENOENT`。GitをWeb Dockerfileへ追加して再build中。
- Dashboard E2Eの失敗4件は旧Reaction Roles設定画面の「パネル投稿先」を待ち続けた。現行Routeは専用画面へRedirectする。チャンネル・複数RoleのSnowflake保持という検証内容を現行Suggestions Pickerへ移し、Welcomeの日本語表示確認を維持した。旧Reaction Roles画面を復活させていない。
- 内部文書 `EXECUTION_PLAN.md` / `PROGRESS0910.md` / `TESTING.md` をVitePress生成対象から除外した。開発履歴を公開Docsへ混ぜず、リポジトリでは保持する。
- uv 0.8.22で作業ディレクトリへWindows Python 3.13.7を導入。`.venv-p013` に同じrequirements.lockを `--require-hashes` でinstallし `pip check` 成功。全152テスト成功、33.608秒。ログは `.venv-p0/windows313-install.log` / `windows313-tests.log`。
- CIをLinux/WindowsのPython 3.13全テスト、Python/Webコンテナbuild・実行、WebログArtifact保存へ変更した。Python installはLockとハッシュ検証を使用する。
- 固定Gitleaks v8.28.0 Image（digest `sha256:cdbb7c955abce02001a9f6c9f602fb195b7fadc1e812065883f695d1eeaba854`）でGit履歴を検査。21コミット、約1.95MB、18秒、検出なし。初回Image取得は一時EOFで失敗し再取得成功。検査は `--redact` を指定しCIにも追加した。未コミット差分は履歴検査対象外。
- この時点ではGitHub上のCI自体を実行していない。定義追加とローカル同等検証を区別する。
- P0-3残作業：Git追加後のWebコンテナbuild完了確認と全6検査の再実行、失敗原因の解消・Baseline記録。P0-4以降は未着手。

## P0-3 — Web再検証

- Git追加中に変更したE2E・VitePress設定がbuild開始時のソースSnapshotに含まれていないことをImage内ファイルで確認した。修正前Imageの `tueka-web-baseline-0910-second` を停止し、依存レイヤーを再利用して最新ソースで再buildした。観測タイムアウトを理由に再起動したものではない。
- 最新ソースで6検査を再実行。Node v24.21.0、Web Image digest `sha256:0f5b15c26538add483ce83803de2f364ca7bddb897fc0ac9c7be6ee6de5813cf`。
- 型検査成功7.001秒、Vitest 10件成功2.939秒、Frontend build成功10.987秒、Docs build成功5.770秒、Docs Playwright 10件成功13.208秒。
- Dashboard Playwrightは24成功/4失敗32.242秒。テストの `getByLabel('メンバー')` がRole checkboxと投票switchへ一致した。Role checkboxをexact名で指定するよう修正した。
- 最後の変更はE2Eのlocator2箇所のみ。その変更を含むImage digest `sha256:6cab92ed2c61f22106a8787ade5cd3593666799771f95d8c840cda68a2739cb5` をbuildし、Dashboardの全28件を再実行中。
- 6検査のログ・summaryは `.venv-p0/web-baseline-final/`、Dashboard再検証ログは `.venv-p0/dashboard-verified.log`。内部文書除外によりDocs buildのdead-link検証は有効のまま成功した。
- CI YAMLをパースしpython/containers/secretsの3ジョブを確認。`node --check scripts/web-baseline.mjs` 成功。GitHubでの実行結果とは扱わない。

## P0-3 — 完了判定

- Dashboard Playwrightの再検証は28件成功、36.3秒、終了コード0。実行コンテナ `tueka-dashboard-baseline-0910` は終了した。
- Pythonコンテナ152件、Windows Python 3.13で152件、Vitest10件、Dashboard Playwright28件、Docs Playwright10件、型検査・Frontend/Docs buildが成功した。各実行の版・digest・所要時間は上記記録に対応する。
- CIへPython 3.13 / Windows、ハッシュ付きLock、コンテナbuild・検証、秘密情報検査、Webログ保存を追加した。ローカルで対応検証を行った。リモートCIは未実行。
- 判定：P0-3のBaseline取得・CI定義整備を完了。StageでのDiscord/OAuth/Webhook実動、運用DBのBackup/Restore、全Phaseリリース判定は未完了。
- 次の着手はP0-4。DBの配置・SchemaとV1/V2読書き箇所を調べ、整合したBackupと別DB復元を検証し、削除Inventoryを作成する。運用DBへのアクセスが確認できない場合は、その未検証境界を明記する。

## P0-4 — ローカル設定先DBの保全・Inventory

- 現在の作業ツリーと前回P0-3完了記録を確認。前回はテスト・CI整備を伴う進捗。
- `.env` のDB/Dataパス項目だけを確認し、設定先が `data/tueka.sqlite3` / `data` と一致することを確認した。Token等は出力していない。別の遠隔本番DBの配置・一致は未確認。
- `scripts/db_inventory.py` を追加。sourceはSQLite URI `mode=ro` で開き、Backup APIを使って新規Snapshotへ保存する。既存出力は上書きせず、存在しないsourceを空DBとして作成しない。
- inventoryは列、Index、外部キー、件数、Schema version、integrity/foreign-key結果だけを返し、行内容や違反行IDを出力しない。Backup後の検査に失敗した場合はその新規Snapshotを除去する。
- `tests/test_db_inventory.py` の4件がWindows Python 3.13.7で成功、0.221秒。未checkpoint WALの取込み、別DB復元と内容保持、秘密の行内容をMetadataへ含めないこと、missing source、既存出力保護、FK違反拒否・source不変を検証した。
- ローカルDBを `data/backups/p0-0910/snapshot.sqlite3` へBackupし、`restored.sqlite3` へ復元。両方とも69テーブル・101行、integrity成功、FK違反0件。両inventory JSONは一致した。
- Snapshot/復元DBのSQL dumpをメモリ内でハッシュ比較し内容一致を確認した。dump内容はファイルやログへ出力していない。ローカルTranscriptディレクトリはファイル0件だった。S3・鍵世代の復旧は検証していない。
- `docs/inventory/schema-0910.json` に69テーブルのMetadata、保持/削除判定、Runtime Pythonの静的SQL参照位置を保存。`docs/inventory/V1_INVENTORY.md` に削除順・共有テーブル・列単位の注意点を整理した。Inventoryは公開Docs生成から除外した。
- `moderation_points` の旧Rules/Events向けFKを先に解消し、V2のRule/Event列を保持する必要がある。共有のCase/Point/XP/設定テーブルは表全体を削除しない。現行のSuggestions 3テーブルはこのDBには未作成のため、新規Migrationで保持・作成対象として記録した。
- Backup/Restoreツールの使用方法とTranscript等の対象外資材を正式Backupページに追加した。
- 判定：現在アクセスできるローカル設定先についてP0-4のSnapshot・復元・削除Inventory作成を完了。遠隔本番DBへの破壊的Migrationは、その環境での新しいSnapshot/Inventory検証を別途条件とする。
- 次はP1-0の最小番号付きMigration基盤。実DBへの削除はまだ実施していない。空DB・Snapshot複製のFixtureで適用履歴、Snapshot、Transaction、途中失敗Rollback、再適用を検証してからDomain単位のV1除去へ進む。

## 2026-09-11 — P1-0 番号付きMigration基盤

- 実装：`migrate.py` と `migrations/0001_suggestions.sql` を追加。0001は既存Suggestions仕様の3表・Indexを作成し、V1表は削除しない。
- `BEGIN IMMEDIATE` で書込みを直列化し、DDL実行前に別のread-only接続からSnapshotを取得する。未適用ファイル全体と履歴更新を一つのTransactionで実行する。
- `schema_migrations` に番号・ファイル名・改行正規化後SHA256・日時を記録。適用済みファイル改変、番号欠落、不一致履歴を拒否する。再適用時は更新・新Snapshotとも発生しない。
- SQL内のTransaction制御、PRAGMA、ATTACH/DETACHをauthorizerで拒否。Migration内COMMITが失敗時Rollbackを無効化しないことを検証した。
- ローカルDBの保全Snapshotを `data/backups/p1-0911/fixture.sqlite3` へ複製して0001を適用。元69テーブルの全行内容が一致し、追加後73テーブル、整合性成功・FK違反0件。再適用結果はapplied空配列、snapshot null。原運用DBには適用していない。
- Migration専用テストは最初の7件がWindowsで0.487秒、Linuxで0.384秒ですべて成功。並行実行・初期化互換性の2件を追加後、Windows Python 3.13.7で9件成功、0.467秒。
- 最終回帰：固定Linux Python 3.13環境に現在ソースをread-only mountし、全165テスト成功、50.408秒。ログ `.venv-p0/p1-migration-linux-tests.log`。
- `docs/operations/migrations.md` を追加し、停止・Stage/複製DBでの事前検証・Snapshotの範囲・Rollback・追加規約を記載。Docsナビゲーションへ追加。Docs build成功、10.38秒。
- レビュー観点：Backup失敗時はDDLなし、途中DROP/CREATE失敗後にデータ/Schema/履歴が元に戻る、FK失敗Rollback、同時Runnerが一度だけ適用、既存V2データ保持、再適用不変、コンストラクタ再初期化と0001のSchema一致を確認した。
- 作業中に既存変更がCommit `c110970` へ取り込まれたことを確認した。こちらからCommit・Reset・巻戻しは行っていない。
- 判定：P1-0の基盤実装・テスト・レビューを完了。既存Domain全体のDDL CLI統一はPhase 2の対象。V1削除時の再作成防止は、そのDomainのRuntime参照/旧DDL削除と番号付きMigrationを同時に実施し、再初期化テストで確認する。現時点でV1表は未削除。
- 次の作業単位はP1-1：Dashboard SPA常時化、旧管理画面・旧保存Route除去、正式URL/OAuth/CSRF/Guild認可/Docs配信の回帰検証。なるべく一つの作業単位で実装・テスト・レビューまで完了させる。Phase 1全体は継続中。

## 2026-09-11 — P1-1 Dashboard SPA統一

- Dashboard Flag・Guild Allowlist分岐、旧管理テンプレート8件、旧CSS/JavaScript6件、旧保存Routeと互換Redirectを除去。公開ランディング・404・認証・Webhookは保持した。
- 現行SPAのURLを明示的に配信し、未知・廃止URLは404、Frontend未buildは503、SPA HTMLは再検証必須とした。APIの `/api/v1` は現行契約として維持した。
- 旧保存処理の必須入力・Bot権限検証を汎用V2保存APIへ引き継いだ。Audit MemberのView Audit Log不足を保存拒否するAPIテストへ置き換えた。
- レビューで旧Social OAuth開始URLの残存を検出。認証処理を `/social/oauth/{provider}/connect/{guild_id}` へ移し、旧管理フォームURLは廃止。callback URLは保持し、戻り先は現行SPAに変更した。新開始RouteのCSRF未設定拒否を検証した。Providerとの実接続は未検証。
- Windows Python 3.13の全170件成功（38.283秒、`.venv-p0/p1-dashboard-python.log`）。その後のOAuth開始URL変更と追加テストについて配信・認証テスト6件成功（1.787秒）。最終差分全体で171件を再実行したとは扱わない。
- Frontend型検査・build成功、Vitest10件成功。進行中だったDashboard Playwrightの終了コード0を回収し、28件成功・57.2秒を確認した。Docs build成功、Docs Playwright10件成功・22.6秒。最後のアーキテクチャ説明追加は文章のみであり、このDocs build後の変更。
- 配信回帰では正式URL、旧Flag無視、未build503、旧URL/POST廃止、OAuth state再利用拒否、セッション・ログアウト、Guild拒否、公開画面、UI資産・Docsヘッダーを確認。`git diff --check` 成功。外部StageのOAuth/Discord実動は未実施。
- README、環境変数、design、更新資料をSPA常時化へ同期。変更は未コミットのまま保持し、他の既存差分を巻き戻していない。
- 判定：P1-1の実装・ローカル回帰・レビューを完了。Phase 1全体は未完了。次はP1-2のTicket V2固定と旧Ticket/平文Transcript移行除去、番号付き削除Migration、空DB・V2/混在Fixture・再起動検証。

## 2026-09-11 — P1-2 Ticket V2固定と旧処理削除

- 前回はP1-1の実装・検証と進捗記録を完了。現在の作業ツリーを再確認し、P1-2を継続した。
- `config.py` のTicket切替Flag/Allowlist、CogとAPIの切替判定を削除。受付の有効・無効はV2のGuild設定で管理し、受付停止時も既存Ticketと保留処理を保持する。
- Community Cogから旧Ticket作成・旧ボタン・`publish_ticket_panel` / `close_ticket` の旧コマンドとV2委譲を削除。Tickets Cogの旧 `tueka-ticket:create` Fallbackを削除し、現行 `tueka-ticket:open:<id>` と `/ticket` / `/t` を維持した。
- Repositoryの旧Ticket自動Import、移行済み判定、平文Transcript読出し・クリア処理、Serviceの暗号化移行、定期処理からの移行呼出しを削除。GuildStorageの旧Ticket CRUD/DDLも除去した。
- `0002_remove_legacy_tickets.sql` は `support_tickets` / `ticket_migrations` の2表だけをDROP。V2 Panel/Ticket/Transcript/Outbox/Scheduleと共有設定表は保持する。Runtime再初期化で旧2表は復活しない。
- Feature一覧のTicket表示をV2設定から取得し、V2保存時の旧共有設定への二重書込みを除去。汎用Module保存のTicket受付を廃止し専用APIへ統一した。
- API回帰で初回保存のrevision競合漏れを検出。未保存revisionを0、初回保存を1にし、設定APIではrevision必須・不一致409にした。旧Flagがfalse、旧Allowlistが不正形式でもV2 APIが動き、認証・Guild/Staff権限・CSRFを維持することを確認した。
- `test_ticket_migration.py` は空DB、直前0001から混在DBへの適用、V2専用DB、再適用、再初期化、DROP後の失敗Rollbackを検証。混在Fixtureでは全保持表の行内容と暗号化Blobを比較し、Transcript復号・Outbox再取得・Schedule読出しを確認した。
- ローカル保全Snapshotを `data/backups/p1-ticket-0911/fixture.sqlite3` へ複製し0001/0002を適用。保持67テーブル・100行一致、integrity成功、FK違反0、再適用applied空配列。原DB・原Snapshotは変更していない。旧データは適用前自動Snapshotに保持される。
- 初回全体検証では旧CRUDを呼ぶ既存テスト、追加Thread Fixtureの必須項目漏れ、Linuxの既存0.24秒判定が失敗。旧テストを現行Domain検証へ置換、Fixture修正、並行通信テストをBarrier方式へ変更した。全リクエスト開始前は応答せず、直列化なら失敗する検証へ置き換えた。
- 最終全体検証：Windows Python 3.13で178件成功・36.124秒、固定Linux Python 3.13コンテナで178件成功・66.891秒。ログ `.venv-p0/p1-ticket-windows-verified.log` / `p1-ticket-linux-verified.log`。その後BotのCog読込みテストを1件追加し、Migration関連6件成功・0.721秒。現行計179件全体を再実行したとは扱わない。
- Bot読込みテストはDiscord接続なしでCommunity/Tickets Cogをloadし、旧Flag属性なしで `/ticket` / `/t` が登録され、旧コマンド・旧Schemaが復活しないことを確認した。実Guild上のCommand同期・Channel/Thread操作はStage検証として残る。
- Docs build成功・12.28秒、Docs Playwright10件成功・28.0秒。正式Ticketページへ鍵・起動・移行・復旧説明を移管し、旧Flag/旧コマンド案内を削除。README・Linux起動・更新・復元手順に番号付きCLIを反映した。Frontendコードは本単位では変更していない。
- 作業中に既存差分がStageされたことを確認。こちらからCommit/Stage/Resetは行っていない。追加テスト・記録の差分はそのまま保持する。
- 判定：P1-2の実装・ローカルテスト・レビューを完了。遠隔本番DB、Stage Discord/OAuth、S3復元は未検証。Phase 1全体は継続中。
- 次はP1-3：Reaction RolesのSafety旧ボタン・旧Panel保存、API Legacy表示/Wizard、旧公開コマンドと旧参照を除去し、`reaction_role_panels` の削除Migrationを追加する。V2設定・マッピング・付与状態・期限・修復を保持し、共有 `guild_modules` は巻き込まない。

## 2026-09-11 — P1-3 Reaction Roles旧処理削除

- 前回P1-2の完了記録と現在のStage済み差分を確認して着手。既存差分のCommit/Stage/Resetは行っていない。
- Safety Cogの旧 `publish_reaction_roles` コマンド、`tueka-rr:` ボタンlistener、GuildStorageの旧Panel CRUD/DDLを削除。現行 `/reactionrole` / `/r` とNative Reaction処理は維持した。
- ReactionRoleRepositoryの `guild_modules` 参照を除去。既存V2の有効メッセージから不足設定行を補う処理は維持し、明示的な無効設定を上書きしない。V1設定だけのGuildは自動有効化しない。
- Overview APIの `legacy` 応答、FrontendのLegacy表示・移行Wizard・日英翻訳・専用CSSを削除。Registryの旧入力項目も除去し、Feature一覧はV2設定から取得する。
- 専用設定保存の旧共有設定への二重書込みを除去。汎用Module APIのReaction Roles保存は404とし、現行専用APIへ統一した。認証・Guild認可・CSRF・revision競合の回帰を追加した。
- `0003_remove_legacy_reaction_roles.sql` は `reaction_role_panels` のみDROP。V2設定・メッセージ・マッピング・付与状態・期限・Outbox・復旧記録と共有設定表を保持する。
- 新規Migrationテストで空DB、0002からのV2専用/混在DB更新、全保持表の行一致、再初期化、再適用、Snapshot内旧データ、後続SQL失敗時のDROP Rollbackを確認。適用後の期限取得・Outbox取得・付与状態・復旧記録も確認した。
- ローカル複製DBを `data/backups/p1-rr-0911/fixture.sqlite3` に作り0003を適用。保持69テーブル・100行一致、integrity成功、FK違反0、再適用applied空。原DBと前段の保全Fixtureは未変更。
- Windows Python 3.13全182件成功・25.192秒、固定Linux Python 3.13コンテナ全182件成功・39.896秒。ログ `.venv-p0/p1-rr-python.log` / `p1-rr-linux.log`。
- Frontend型検査/build成功（Vite 7.02秒）、Vitest10件成功（3.07秒）、Dashboard Playwright32件成功（1.3分）。追加E2EはLegacyフィールドなしのOverview、空状態、作成画面への遷移、4画面幅、重大Accessibility違反なしを検証した。
- Docs build成功・60.72秒、Docs Playwright10件成功・18.6秒。正式Reaction RolesページとCommand/Migration資料を更新。Docs E2Eは既存のトップ/検索/長文Ticketページの共通回帰であり、全Docsページの視覚検査ではない。
- レビューでReaction Rolesの旧DB参照・旧ボタン・Wizardの残存なしを確認。現行各Type、Link、期限、修復、Discordコマンド読込みは既存テストも含めて成功。最後の変更は末尾空行とCogの説明文のみ。`git diff --check` 成功。
- 判定：P1-3の実装・ローカル検証・レビューを完了。実GuildのRole付与/解除・Command同期、Stage、遠隔DB適用は未実施。Phase 1全体は継続中。
- 次はP1-4：旧AutoMod listener/評価、CSV Import、旧警告・旧イベント移行Fallbackを除去。旧Rule/EventへのFKと旧ID列を先に解消し、現行Rule/Case/Point/Event/期限付き解除を保全する削除Migrationを追加する。共有Case/Point/XP表全体は削除しない。

## 2026-09-12 — P1-4 Moderation旧処理・旧Schema削除

- 前段では旧CSV読込み・起動時Import・停止済みlistenerと旧閾値Fallbackを除去し、184件の回帰成功を確認。その作業を継続して旧SQL・旧列の削除まで実施した。
- AutoMod Cogの起動時V1/V2自動移行、禁止語CSV読込み、旧Evidence定期削除を除去。Moderation/Safety Cogの停止済み旧listenerと旧フィルター補助処理を削除し、`BANNED_WORDS_FILE` を設定・環境資料から除去した。
- GuildStorageの旧AutoMod Rule/Event CRUD・移行判定・旧Warningカウンタ操作を削除。Case/Pointの旧ID引数・書込み、Serviceの旧ID参照と未使用の旧実行/ログ経路も除去した。
- Point閾値処置は有効なInfractions設定だけを使用し、旧AutoMod閾値・旧段階処置へFallbackしない。警告の応答は現行の有効Point合計を使用する。XPは保持し、JSON Importの旧warn書込みも除去した。JSON移行自体はP1-5で削除予定。
- `0004_remove_legacy_moderation.sql` を追加。旧 `automod_rules` / `automod_events` / `automod_migrations` / `moderation_migrations`、Case/Pointの旧ID列、Ruleの `legacy_rule_id`、`guild_users.warn` を削除する。
- Ruleの再作成時にON DELETEが現行Event/処置結果を変更しないよう、対象6表の保持列をTransaction内の作業表へコピーし、子→親の順でDROP、親→子の順で復元する。Index・制約を再作成し、作業表を除去する。SQLiteの外部キー検査は無効化していない。
- `tests/fixtures/moderation_pre_p1.sql` は保全DBから確認した旧Schemaのみを含み、ユーザー行は含まない。新規Migrationテストで空DB、直前0003からV2専用/混在DB、保持列全行一致、Rule/Event/処置結果の関連付け、Case/Point/XP/期限付き解除、再初期化、再適用、失敗時Schema/データ/履歴Rollbackを確認した。
- 旧CRUDテストは現行Rule/Event CRUD・Evidence保持期限・重複拒否の検証へ変更。旧移行成功テストは削除Migrationの保持/破棄検証へ置換した。旧regex補助テストは旧listener非登録の検証へ変更し、現行Regexエンジンの検証は維持した。
- Point Actionの実行テストを追加し、旧Rule引数がなくても処置がsuccessとなり、現行Rule/Eventに紐づくCaseとPointが保存されることを確認。Infractions無効時の旧閾値非実行と、CSVパス属性なしのCog読込み・DB不変も確認した。
- ローカル保全Fixtureを `data/backups/p1-moderation-0912/fixture.sqlite3` へ複製し0004を適用。保持65テーブル・98行の保持列が一致、integrity成功、FK違反0、再適用applied空。原DB・原Snapshotは未変更。
- 最終全体検証：Windows Python 3.13で186件成功・21.478秒、固定Linux Python 3.13コンテナで186件成功・30.248秒。ログ `.venv-p0/p1-moderation-windows-final.log` / `p1-moderation-linux-final.log`。Docs build成功・5.68秒。
- 正式Moderation/AutoMod/Infractions・Migration・環境資料へ、設定正本、削除対象、停止/Backup、RollbackとDiscord処置の突合を反映。Frontendは本単位では変更していない。
- レビューでRuntimeから旧Rule/Event/移行判定/CSV参照がなく、旧列のDDL再作成もないことを確認。`git diff --check` 成功。作業途中にP1-3がCommit `5f3f139` へ取り込まれたことを確認し、既存変更を巻き戻していない。
- 判定：P1-4の実装・ローカルテスト・レビューを完了。StageでのDiscord実処置/期限付き解除・遠隔DB適用は未実施。Phase 1全体は未完了。
- 次はP1-5：JSON移行不要を現在のInventoryで確定し、`migrate_json.py` / `migrated` / JSON移行済み判定を除去。残存V1設定Fallback・Schema・一時文書を点検し、必要情報を正式Docsへ移管して起動/更新/復旧を番号付きCLIへ統一する。Bot/Dashboard/Worker再初期化後の旧構造非復活とPhase 1の全体出口条件を検証する。

## 2026-09-12 — P1-5 JSON・共有設定・一時文書の整理（継続中）

- 実行計画を現在のコードと進捗へ照合し、古い「P0-1から着手」を修正。P2以降の依存と受入条件を作業単位に分けた。P1-4までの完了記録を保持し、Commit/Stage/Resetは行っていない。
- ローカル `data` 直下のJSONは0件。`migrate_json.py`、GuildStorageのJSON Import・移行済み判定を削除。JSONファイルを置いてもXPへ取り込まないことをテストした。遠隔本番のJSON有無は未確認。
- `0005_remove_shared_settings_fallback.sql` を追加。V2が現在参照するWelcome / Autorole / Leveling / Audit設定の実効値を `guild_modules` に固定してから `guild_settings` を削除する。`app_metadata` 自体は保持し、JSON移行マーカーだけを削除する。
- GuildStorageの共有設定CRUD・get/setラッパー・読込時Fallbackを削除。`set_management` の共有設定への二重書込みを除去。明示null、既存設定、有効状態、revisionを維持し、未保存の候補は無効・revision 0で保存する。既存Auditのカテゴリ未指定によるメッセージログはMigrationで明示値に変換し、新規設定はカテゴリの明示選択を必要とする。
- 新規Migrationテストで設定・XP・他Metadata保持、直前0004からの更新、再適用、Snapshot、途中失敗時の全Dump一致、再初期化、空DBを検証。新規テーブルのenabled制約も確認した。既存のMigrationテストは0005を含む適用順と後続失敗SQL番号へ更新した。
- `test_v2_startup.py` はBotの全16 ExtensionとCommand登録、Dashboard lifespan、SocialWorker初期化を同一DBで2回実行し、旧表/旧列の非復活とSchema不変を確認する。DiscordのCommand同期だけをMockし、実Discord接続・Provider通信・配送Loopの実動を証明するものではない。
- 初回の指定モジュール実行でReaction Rolesテストの既存import方式が失敗したため、CIと同じ `unittest discover -s tests` で全体を実行した。最終Windows Python 3.13は189件成功・18.119秒。ログ `.venv-p0/p1-cleanup-windows-final.log`。
- 保全DBの複製 `data/backups/p1-cleanup-0912/fixture.sqlite3` に0005を適用し、変更前実装と比較した16組の機能設定の実効値、保持62表81行、他Metadataが一致。制約調整後の最終SQLは原保全DBから別途作った `final.sqlite3` に適用し、検証済み候補との全データ一致、integrity成功、FK違反0、再適用なしを確認した。初期候補は最終SQLとchecksumが異なるため、以後の継続検証には `final.sqlite3` を使用する。原DB・前段の保全DBは変更していない。
- `PROGRESS0814.md` / `DEPLOYMENT_TODO.md` / `FEATURE_MODULE_GUIDE.md` / `TICKETS_V2.md` を削除。現行の操作・復旧説明は正式Docsに保持し、実環境確認はLinux運用ページへ移管した。VitePressの旧文書除外指定・文書テストの旧例外を除去。README、日英導入、Linux、更新、復元を番号付きCLIへ揃え、導入はPython Lockとnpm ciへ統一した。
- Frontend型検査/build成功（Vite 4.11秒）、Vitest10件成功（3.96秒）。ログ `.venv-p0/p1-cleanup-frontend-build.log` / `p1-cleanup-vitest.log`。Frontendソース変更はない。`git diff --check` 成功。
- Linuxコンテナ全PythonテストとDocs buildは、自動承認レビューが使用量上限で失敗して起動されなかった。許可済みFrontend検証はsession 29658から完了結果を回収した。拒否された操作を別経路で迂回していない。再実行の承認をユーザーへ依頼した。Dashboard/Docs Playwrightも本単位では未実行。
- 残存調査で `storage.initialize` のSocial旧購読→Target/Template変換、Provider Moduleの自動作成、未使用の旧 `save_social_subscription` とEventラッパーを確認。`tests/test_social_worker.py` の旧購読自動移行成功テストも残る。YouTubeの旧Custom URL解決は外部URL仕様への対応であり、V1アプリ互換とは区別する。Reaction Rolesの不足設定行補完は既存V2メッセージの修復として前段で保持したもの。
- 次の作業：Socialの現行V2データ・読書き経路をInventoryし、旧購読変換と旧APIラッパーを除去する。必要なSchema処理は番号付きMigrationと同じ単位で扱い、現行購読・Target・Cursor・配送・期限処理を保持する。その後、Linux全Python・Docs build・Dashboard/Docs Playwrightを実行し、P1-5/Phase 1の出口を再判定する。コンストラクタDDL全体の明示CLI移設はP2-1で行う。
- 判定：P1-5は未完了。StageでのDiscord/OAuth/Webhook・遠隔本番DB適用も未実施。Phase 2へはまだ進めていない。現在確認できたテストの成功をPhase 1全体の完成やリリース済みとは扱わない。

## 2026-09-12 — P1-5完了・Phase 1ローカル検証の引継ぎ

- 上記P1-5の継続作業を実施。ユーザーから上限解消後の再実行承認を受け、使用量状態で上限到達なしを確認し、LinuxテストとDocs buildを通常の承認経路で再実行した。最初の拒否は解消済みで、現在実行待ちのプロセスはない。
- Socialの旧購読からTarget/Templateへの起動時変換、Provider Module自動作成、未使用の旧保存/Event書込みを削除。Cogの旧liveイベントへのFallbackと旧live専用分岐も削除した。現行Module設定の明示的な無効状態を起動時に変更しない。
- `0006_remove_legacy_social_template.sql` は購読表を現行列で再作成し、旧単一template列だけを除去する。現行イベント別Template、ID・有効状態・revision・Target/Cursor・Event・配送・Live Messageを保持する。共有表の旧行は他列の値を保持するがTargetを自動生成せず、配送には現行TargetとのJOINを必須にした。純V1 Schemaの自動Importは提供しない。
- Social Migrationテストで直前0005、V2専用/混在Fixture、保持全行一致、再初期化、再適用、Snapshot、後続0007失敗による全DumpのRollbackを検証。旧自動移行成功テストは旧行を変換/有効化せず配送しない検証へ変更した。
- Discord配送テストを追加。旧live購読へlive_startをFallback配送せず、現行live_startは1回送信、live_endは保存済みMessageを編集して追跡を解除することをMockのDiscord Channelで確認した。実Guildの権限・HTTP挙動の検証を代替するものではない。
- 保全DB `data/backups/p1-cleanup-0912/final.sqlite3` を `data/backups/p1-social-0912/final.sqlite3` に複製して0006を適用。保持64テーブル97行の全保持列一致、Runtime再初期化2回後も一致、integrity成功・FK違反0・再適用なし。原DB・前段Snapshotは変更していない。今後の継続検証はこの0006適用済み保全Fixtureを基準にできる。
- 最終全Pythonテスト：Windows Python 3.13で192件成功・30.187秒、固定Linux Python 3.13コンテナで192件成功・38.944秒。ログ `.venv-p0/p1-final-windows.log` / `p1-final-linux.log`。全ExtensionとDashboard/Workerの再初期化では旧Social template列の非復活も確認した。
- Frontend型検査/build成功（4.11秒）、Vitest10件成功（3.96秒）、Dashboard Playwright32件成功（46.2秒）、Docs Playwright10件成功（17.7秒）。最後のSocial Runtime変更はPython全回帰で検証し、Frontendソースは変更していない。Social説明追加後の最終Docs build成功（9.59秒）、ログ `.venv-p0/p1-final-docs.log`。Docs E2Eは共通ページ/検索/長文の回帰で、全運用ページの実操作検証ではない。
- Runtimeの残存参照を点検。Reaction RolesのLink互換性表示とYouTubeの過去URL形式対応はV1アプリ互換ではない。既存V2 Reaction Rolesメッセージから不足設定を補う修復は前段の方針どおり保持する。現行SchemaのコンストラクタDDL/ALTERは残り、P2-1の対象とする。最後の変更は説明コメント・Docs・進捗のみで、`git diff --check` 成功。
- 判定：P1-5のローカル実装・Migration・検証・正式Docs・レビューを完了。Phase 1のローカル開発出口を満たした。Stageの実Discord/OAuth/Webhook、遠隔DB適用、実Transcript/S3復元は未実施であり、リリース承認・本番移行完了とは扱わない。Goal全体はPhase 2〜5を含めて継続中。
- 次はP2-1：全Repositoryの接続/DDL/ALTER/起動時更新を棚卸しし、共通DB層と後続Migrationへ移す。既存0001〜0006を改変せず、空DB・現在のV2 Schema・直前版更新を検証する。Runtimeは未適用Schemaで明確に失敗させ、テストFixtureも明示Migrationへ切り替える。P2-2のDomain分割はこの受入後に進める。Commit/Stage/Resetは行っていない。

## 2026-09-13 — P2-1 共通DB層・明示Migrationへ統一

- P1-5の差分がユーザー側でStageされていることを確認して着手。その後Commit `93756c5` へ取り込まれたことを確認した。既存変更のCommit/Stage/Resetは行っていない。
- GuildStorage、Ticket、Reaction Roles、Suggestionsの初期化結果から現行64テーブル・23IndexのDDLを抽出し、`0007_current_schema.sql` を追加。既存0001〜0006は変更していない。RuntimeからCREATE/ALTER/executescriptと直接sqlite3.connectを除去した。
- `database.py` に接続・Transaction・WAL・busy timeout・読取り専用接続・整合性Inventory・Backup・Schema履歴検査を集約。`migrate.py` と `scripts/db_inventory.py` も共通層を利用する。Inventory CLIの直接実行も確認した。
- 接続の書込み待ちは10秒へ統一（Ticketだけ従来30秒）。WALへの初回切替で並行Migrationの競合を検出したため、既にWALなら切替を省略し、BUSY/LOCKEDだけを上限付きで再試行する。Migrationの同時実行テストと通常Domainの並行処理テストで検証した。
- RepositoryのコンストラクタはDBを自動作成・更新せず、読取り専用の履歴検査で不存在・未適用・checksum不一致をSchemaNotReadyとして拒否する。BotはDiscord接続前に検査する。Dashboard/Workerも保存層生成時に検査し、3起動経路で未適用DBを変更しないテストを追加した。
- 現行Ticketの未完了Close復旧とReaction Rolesの不足設定修復はDomain処理として保持した。Schema変更ではなく、P2-2以降に責務を再評価する。Repositoryの接続メソッド名は呼出し契約を維持し、内部を共通Transactionへ委譲した。
- 元の初期化処理にあった39件の条件付き列追加を0007へ移設。`-- tueka: add-column-if-missing` 注釈付きの単一ALTERだけをCLIが扱い、既存列は値/定義を変更せず、不足列を追加してからIndexを作成する。Schema照会はCLI自身が行い、Migration本文のTransaction/PRAGMA/ATTACH制限は維持する。注釈もSQL checksumに含める。
- 条件付き列追加の初回テストで正規表現Matchの取り出しミスを検出して修正。不足列追加、既存値保持、不正注釈の拒否、Rollback、旧V2の不足列をCLIで補った後の起動を確認した。
- `tests/db_support.py` でRuntimeテストのDBを明示Migrationで準備するよう変更。旧版Migrationテストは現行データを準備した後に旧DDL/履歴のFixtureを構成し、Runtimeで旧版DBを自動初期化する前提を除去した。Moderationは記録済みの旧Schemaを再構築して、元の旧FK/列と現行行の保持検証を継続する。
- 回帰でWindowsのFixture接続未Closeと、廃止したSuggestionRepository._connectへのテスト依存も検出。接続を明示Closeし、投票の書込みロック検証は共通database.connectを監視する方式へ変更した。状態読取り前に競合書込みを拒否する検証内容は維持する。
- 共通DBテストは不存在DBを作らないこと、未適用/不正履歴で全Dump不変、全RepositoryのWAL/FK/timeout一致、再初期化不変、成功Commit、IntegrityErrorとKeyboardInterrupt時のRollbackを検証する。
- 最終全Python回帰：Windows Python 3.13で200件成功・37.313秒、固定Linux Python 3.13コンテナで200件成功・44.069秒。ログ `.venv-p0/p2-final-windows.log` / `p2-final-linux.log`。Docs build成功・9.75秒、ログ `.venv-p0/p2-docs.log`。Frontendソースは変更していないため、本単位ではFrontend/Playwrightを再実行していない。
- P1保全DBから `data/backups/p2-schema-0913/final.sqlite3` を作り最終0007を適用。保持64表97行、列・FK・IndexのMetadata一致、整合性成功・FK違反0、全Repository生成後も保持、再適用なし。原DB・P1保全DBは変更していない。`p2-schema-0912` は条件付きALTER追加前の開発途中候補でchecksumが異なるため、継続検証には9/13のfinalを使う。
- Inventory CLIの最終結果は履歴表込み65表104行、整合性成功・FK違反0。Migration CLIの再実行はapplied空・snapshotなし。Runtimeの4Repositoryに直接接続/DDLが残らないことを検索確認し、`git diff --check` 成功。
- 正式Architecture・機能追加手順・Migration資料へ、共通DB境界、起動時拒否、条件付き列追加、テストDB準備を反映。最後の変更は進捗と実行計画のみ。
- 判定：P2-1のローカル実装・テスト・Docs・レビューを完了。Phase 2全体は継続中で、Stage・遠隔本番DB適用は未実施。次はP2-2としてDashboardのSession/OAuth state/Preferences・Guild設定からDomain別Repositoryへ分離し、Community→Engagement→Social→Moderationへ依存順に進める。Ticket Serviceの直接SQLも移設対象とする。

## 2026-09-13 — P2-2 Dashboard認証・個人設定の分離（継続中）

- 現在の差分を保持して、GuildStorageのSession・Discord OAuth state・Preferencesの7メソッドと呼出し箇所を確認。`dashboard/repository.py` のDashboardRepositoryへSQLを移し、GuildStorageから該当メソッドを除去した。旧保存層への委譲や継承は追加していない。
- DashboardのHTML/OAuth経路とJSON APIが専用Repositoryを直接使用する。共通database.pyのTransaction・Schema検査を利用し、Schema変更・追加Migrationはない。SocialのProvider OAuth stateは別DomainとしてまだGuildStorageに残る。
- 既存のStorage/APIテストも専用Repositoryへ切り替えた。専用テストでSession期限境界・失効・再生成後の読取り、期限切れOAuth stateと並行消費の一回性、個人設定のユーザー分離・保存再読込・revision競合を確認した。共通DBの起動拒否/接続設定テストにも新Repositoryを追加した。
- 初回回帰で新importがfuture importより前に置かれた問題を検出し修正。最終全PythonテストはWindows203件成功・44.148秒、固定Linuxコンテナ203件成功・60.163秒。ログ `.venv-p0/p2-dashboard-windows.log` / `p2-dashboard-linux.log`。実Discord/OAuth実動を行ったとは扱わない。
- Architectureに現在の保存境界を反映し、`git diff --check` 成功。Frontendソース・Schema・保全DBは変更していない。本単位ではFrontend/Docs build・Playwrightは再実行していない。
- 判定：Dashboard認証・個人設定の分離を完了したが、P2-2全体は未完了。次はGuild設定の保存とDomain固有正規化の境界を整理し、Community→Engagement→Social→ModerationのRepository分離とTicket Serviceの直接SQL移設へ進む。API URL・認可・保存往復・revision・無効化を維持する。既存差分のCommit/Stage/Resetは行っていない。

## 2026-09-13 — P2-2 Guild設定の保存・正規化を分離（継続中）

- 現在の作業ツリーを確認して継続。Guild Moduleのget/set/module_enabledを `guild_settings/repository.py` へ、7種の既定値/正規化関数を `guild_settings/models.py` へ移した。Schema・保存形式・既定値の動作は変更していない。
- Dashboard APIのModule表示/保存・Social機能切替・Moderation有効判定はGuildSettingsRepositoryを直接利用する。未分離のCog向けにはGuildStorageの3メソッドを委譲窓口として一時的に残した。巨大保存層への新しい設定SQL追加は不要になったが、P2-2全体の分離はまだ完了していない。
- ModerationのRule更新と同じTransactionで実行するguild_modules更新は維持し、純粋なmoderation_settings関数だけを参照するよう変更した。Transactionを分断しないため、そのSQLはModeration Repositoryへ移す単位で整理する。有効Guild一覧やTrust連携の直接SQLも残作業として把握した。
- 専用テストでGuild分離、無効化時の設定保持、再生成後の読取り、revision競合、DBを使わない正規化・入力辞書の非変更を確認。共通DBの起動拒否・接続ポリシーテストにもGuildSettingsRepositoryを追加した。
- 最終全Pythonテスト：Windows205件成功・44.648秒、固定Linuxコンテナ205件成功・60.484秒。ログ `.venv-p0/p2-guild-windows.log` / `p2-guild-linux.log`。Architectureへ保存境界と一時委譲・未分離部分を明記し、`git diff --check` 成功。Frontend/Schema/保全DBは変更せず、本単位のDocs build・Playwright再実行は行っていない。
- 次はCommunity側の一時VC・レベリング等の保存と呼出し先を整理する。有効Guild一覧は設定Repositoryへ移し、Cogが設定とDomain保存を明示的に使う構成へ進める。続いてEngagement、Social、Moderation、Ticket Serviceの直接SQLを扱う。P2-2・Phase 2・Goal全体は継続中。Commit/Stage/Resetは行っていない。

## 2026-09-14 — P2-2 Domain別Repository分離を完了

- 前回までのDashboard認証・個人設定、Guild設定の分離に続き、Community→Engagement→Social→Moderationの順にSQLと呼出し先を整理した。Domainの途中で本単位の完了とはせず、Ticketの直接SQL移設と全回帰まで実行した。
- `community/repository.py` に一時VC・テキスト/音声XPの9メソッド、`engagement/repository.py` にPollの4メソッド、`social/repository.py` に35メソッド、`moderation/repository.py` に37メソッドを配置。有効Guild一覧はGuildSettingsRepositoryへ移した。接続・Schema検査は全9種類のRepositoryが共通database.pyを使用する。
- Cogは設定とDomain保存を明示的に生成し、ModerationServiceには両Repositoryを注入する。Dashboard APIはDBパスから必要なRepositoryを直接生成。HTTP URL・認可・CSRF・revision契約は維持した。旧GuildStorageと一時委譲窓口を含む `storage.py` を除去した。
- ファイル構造をDomain構造へ合わせ、Socialのモデル・暗号化・Provider・Webhook・Worker実装を `social/` に移設。`social_worker.py` は既存CLIを維持する薄い入口とした。従来 `automod/` にあったモデル・Engine・Adapter・ModerationServiceは `moderation/` に統合し、呼出しとテストのimportを更新した。
- ModerationのRuleとrules_revision、CaseとTrustイベントは同一Transactionを維持した。移設した85メソッドのSQL文字列をHEADの旧保存層とAST比較し、変更0件を確認。Schemaと0001〜0007は変更していない。
- Ticket ServiceのBlacklist照会に加え、Cogの当番一覧・Panel移動・Tag・自動Close除外・削除記録もTicketRepositoryへ移した。Service / Cog / API / Workerに直接SQLやRepositoryの接続内部呼出しを残さない境界テストを追加した。
- Communityの並行XP加算・Guild分離・一時VC再読込、Pollの投票変更・期限・Message分離、TicketのBlacklist/Guild境界・Tag正規化・revision/再読込を検証。Audit Logが設定だけでなくModerationイベントを書き込むことを特定し、専用保存先へ接続してDiscord送信後の永続化テストを追加した。
- 初回のDomain回帰でテストが旧 `storage` 属性を参照する6件を検出し、実際の設定/Domain境界へ変更。移動後の既存207件が成功した後、新規契約テストを含む最終全回帰を実行した。
- 最終Windows Python 3.13：211件成功・157.608秒。固定Linux Python 3.13コンテナ：211件成功・106.193秒。ログ `.venv-p0/p2-domain-final-windows.log` / `p2-domain-final-linux.log`。Docs build成功・9.82秒、ログ `.venv-p0/p2-domain-docs.log`。Frontend変更はなく、本単位ではFrontend/Playwrightは再実行していない。
- P2-1最終保全DBから `data/backups/p2-domains-0914/final.sqlite3` を新規複製。9種類のRepositoryを2回生成後も元の全SQL Dumpと一致。履歴込み65表104行、整合性成功・FK違反0。検査結果の表示で整数にlenを使ったミスだけを修正して再読取り確認した。原DBと既存保全DBを変更していない。
- 正式ArchitectureにDomain別の配置・Transaction所有・CLIの入口と実装の境界を記載。実行計画の現在地をP2-3へ更新し、過去の調査表は履歴として保持。`git diff --check` 成功。Commit/Stage/Resetは行っていない。
- 判定：P2-2のローカル実装・テスト・正式Docsを完了。Phase 2全体とGoalは未完了。次はP2-3として4DomainのClaim/Lease/Retry/期限処理を比較し、共通Protocol/Runnerと所有者・失効・重複・Dead Letter・Retentionの契約を実装する。必要なSchema追加は0008以降。Discord操作分離はP2-4、Router/UIはP2-5/6へ順番に進む。
- Stage実Discord/OAuth/Webhook、遠隔本番DB適用、実Transcript/S3復元は未実施のリリースゲートとして継続する。ローカルのP2-2完了をPhase 2全体・本番移行・Goal達成とは扱わない。

## 2026-09-14 — P2-3 共通Outbox / Schedule基盤

- P2-2がユーザー側でCommit `c5d9225` に取り込まれたことを確認。現在の作業ツリーを基準に、Ticket / Reaction Roles / Social / ModerationのClaim・Lease・完了・Retryを比較した。Commit/Stage/Resetは行っていない。
- Ticketのprocessing行が再取得されない経路、Socialイベント完了の所有者検査欠落、Moderation要求/期限処理のLease未実装を特定。`jobs/models.py` にClaim・Outcome・JobStore Protocol、`jobs/repository.py` にTransactionと所有権検査、`jobs/runner.py` に共通実行順序を追加した。
- 7 Queue（Ticket Outbox/Schedule、Reaction Roles Outbox/Schedule、Social Event、Moderation Request/Schedule）を同じRunnerへ接続。DomainのPayloadと既存テーブルを維持し、旧Claim/Finish実装を除去した。HandlerはDomain処理とOutcomeを返し、共通Runnerが取得・Lease更新・終了・失敗を担当する。
- BEGIN IMMEDIATE内で1件取得し、所有者と毎回新しいTokenを保存。完了と更新はID・所有者・Token・未失効・processingを照合する。同じ所有者名で再取得しても前回Tokenを拒否。長時間処理中はLeaseの1/3間隔で更新し、Lease喪失時はHandlerをキャンセル・警告してBatchを終了する。次の定期実行は停止させない。
- 試行数は取得時に加算し、最大8回。Retryは15×2^attempt秒、上限3600秒。最終試行のCrashも失効後failedへ移す。failed行をDead Letterとして保持し、自動的に再実行しない。終端日時から30日後にBatch開始時の保守処理で削除し、保留・実行中は対象外とした。
- `0008_job_leases.sql` は不足するToken・Lease・試行数・終端日時を追加し、Claim/Retention用Indexを14件追加。0001〜0007は変更していない。旧Reaction Rolesの完了日時不明な行は、移行直後に削除されないよう移行時刻を補い30日保持する。
- 既存Migration Fixtureの期待履歴を0008まで更新し、故意の失敗Migrationは0009へ変更。初回に先頭コメントが条件付き列追加注釈を隠す問題、続いて旧Schema Fixtureが新Indexを残したまま列削除する問題を検出して修正した。
- 7 Queue共通の失効・同じ所有者の再取得・古い完了拒否・並行取得・Retry上限・Dead Letter・Retention、Runnerの更新・Cancel・Lease喪失、直前0007からPayload保持・再適用を検証した。完了時には元の期限を変更しない契約も確認した。
- 旧Moderation実行イベントがある未完了要求を成功扱いにせず、照合を必要とするfailedにする。共通Queueの排他とDiscord副作用の一回性は区別し、配送記録・外部成功後DB失敗の補償はP2-4でさらに整理する。継続的なSocial Provider監視、Panel公開、Lockdown復元はDomainのライフサイクルとして残る。
- `data/backups/p2-jobs-0914/verified.sqlite3` はP2-2保全DBから新規複製し、最終0008を適用。既存64表の全既存列・行を照合して一致、履歴込み65表105行、整合性成功・FK違反0、再適用なし。原DB・既存保全DBは変更していない。同ディレクトリの `final.sqlite3` は保持日時の調整前候補であり、以降はverifiedを使用する。
- 保持日時調整後のWindows Migration回帰29件成功・8.805秒。途中のLinux回帰は実行中のMigration編集によるSchemaNotReadyを1件検出したため、コードとMigrationを固定して両環境の全回帰を再実行する。途中結果を最終成功とは扱わない。

- 最終固定後の全Python回帰：Windows220件成功・66.597秒、固定Linuxコンテナ220件成功・138.175秒。ログ `.venv-p0/p2-jobs-frozen-windows.log` / `p2-jobs-frozen-linux.log`。途中の失敗ログとは区別する。最終Docs build成功・7.71秒、ログ `.venv-p0/p2-jobs-docs-final.log`。その後の変更は実行計画・進捗記録のみ。Frontendは変更せず、Frontend/Playwrightは本単位では再実行していない。
- ArchitectureとMigration運用資料に共通Queueの対象、処理順序、再試行上限、保持期限、旧版復帰のSnapshot、外部API副作用との境界を反映。最終 `git diff --check` 成功。
- 判定：P2-3のローカル計画・実装・Migration・テスト・正式Docsを完了。次はP2-4。ModerationServiceのDiscord操作をAdapterへ切り出す境界を定義し、Ticket / Reaction Roles / Social / SuggestionsのCog側操作へ順に進む。成功後DB失敗・権限喪失・補償失敗・孤立Resourceの照合と復旧を検証する。Schema追加は0009以降を使用する。
- Phase 2全体・Stageリリース・Goal全体は未完了。実Discord/OAuth/Webhook、遠隔本番DB適用、実Transcript/S3復元は従来の未実施ゲートとして保持する。


### 2026-09-14 P2-4 異常系と途中回帰の検証記録

- P2-4は未完了。P2-5以降へは進んでいない。Moderationの値/Port境界と処置Intent、Ticket作成の孤立Resource記録・復旧、Social配送のReceipt照合、Reaction Roles配送Service/Adapterを実装中。
- Reaction Rolesの移動確定と旧Botメッセージ削除Outboxを同一トランザクションにした。Cogの移動コマンドもOutboxへ予約する。移動後・ACK前の再実行は対象IDとrevisionで照合する。メンバーのキャッシュ欠落時はRESTで確認し、取得失敗を退出済みとして扱わない。
- この時点のコードでWindows全230件（102.952秒）、Linuxコンテナ全230件（149.483秒）、Docs build（12.64秒）が成功。ログ: `.venv-p0/p2-adapter-checkpoint-windows.log` / `p2-adapter-checkpoint-linux.log` / `p2-adapter-checkpoint-docs.log`。承認済みのLinux/Docs再実行は完了した。これはP2-4完了判定ではない。
- その後Provider継続監視を修正。取得ごとに一意な所有者値を発行し、期限切れ/旧取得による完了・削除を拒否する。配送Event追加とCursor更新も所有権確認後の同じトランザクションにまとめた。Schema変更なし。専用20件成功（1.692秒、`.venv-p0/p2-provider-ownership.log`）。この後の差分を先の全230件成功に含めない。
- 残作業: Ticketの作成以外のResource操作とPanel公開の所有権・部分失敗、Reaction RolesのRole変更補償、Suggestions配送と復旧、Lockdown復元の所有権、各Adapter異常系、正式Docs統合、最終コード固定後の全回帰。実Discord/Stage・遠隔本番DB・実S3復元の未検証は維持する。


### 2026-09-14 P2-4 TicketのPanel・Claim・Close復旧

- `ticketing/panel_delivery.py` に公開状態遷移、`ticketing/discord_adapter.py` にPanelの投稿・編集・削除を分離。Cogは1件ずつ取得してServiceへ渡す。取得ごとに一意なLease所有者値を発行し、完了は期限・所有者・revisionを検査する。
- Panel投稿IDを旧投稿削除前に保存し、削除失敗時も旧新両方のIDを保持する。不明な投稿結果はBotの識別印で直近200件を照合し、見つからなければ重複投稿せず保留する。不明状態での同じ投稿先への編集は照合状態を保持し、別投稿先への移動は復旧が済むまで拒否する。
- Claim権限変更をPortへ移設。変更前後を `claim_started` として記録してからAPIを実行する。DBのClaim確定と `claim_finished` は同じTransaction。補償失敗は成功扱いせず残し、起動時に再試行する。人手変更と競合する権限は上書きしない。
- Close確定と `close_resource` Outboxを同じTransactionにした。Transcript存在・closed状態・revision一致時のみResourceを削除/Archiveする。Thread再開はOutboxへ予約し、Discord成功後にDBを更新する。再開コマンドで他GuildのTicketを変更しないよう先にGuildを検証する。履歴取得失敗時はCloseへ進まない。
- 途中のTicket関連26件ではMigrationテストが1件失敗した。新たなClose削除ジョブが先に取得されることが原因で、保持される削除ジョブと既存auto_closeの両方を確認する期待値に修正した。
- 最終固定コードのWindows全237件成功（114.878秒、`.venv-p0/p2-ticket-checkpoint-windows.log`）、Architecture更新後のDocs build成功（11.39秒、`p2-ticket-checkpoint-docs.log`）。Linux結果は同名の `p2-ticket-checkpoint-linux.log` で別途確定する。Schema追加・0001〜0008改変なし。
- P2-4はまだ未完了。残作業はTicket返信/Note/参加者/その他Resource操作、Panel削除時に未確定投稿IDを照合する処理、Claim開始時の状態検査と復旧判定の最終監査、Panel復旧待ちのAPIエラー表示、Reaction RolesのRole変更補償、Suggestions配送、Lockdown所有権、横断異常系・最終全回帰。P2-5以降やPhase完了へ進めない。


### 2026-09-15 P2-4 Ticket配送の追加分離

- 前記Windows237件と同じ固定コードでLinux237件成功（167.407秒、`.venv-p0/p2-ticket-checkpoint-linux.log`）。その後の変更はこの結果に含めない。
- Panelの不明な投稿結果を削除要求後も `delete_uncertain` として保持する。照合した投稿IDを保存してから削除する。復旧待ちの移動はAPIの `panel_recovery_required` / 409で返し、保存TransactionをRollbackする。専用HTTPテスト1件成功（0.880秒）。
- Ticket参加者の追加・削除・Staff参加をOutboxへ統一。Discord操作をAdapter、DB反映をServiceへ移した。RenameもAdapterへ移設。InteractionのGuildとTicketのGuildを操作前に照合する。
- 返信・Staff Noteの投稿処理をService/Adapterへ分離。送信Intentと識別印で結果不明時を照合し、内部Noteは配送Keyで二重記録を防ぐ。配送KeyはOutbox IDとcreated_atで、保持期限後の数値ID再使用も区別する。確実な未送信失敗は再送可能、照合失敗は不明状態を維持する。
- 回答待ちCategoryと復帰をOutboxへ移し、移動前後をAPI前に永続化する。Discord成功後のDB失敗で復帰先Categoryが壊れないことを検証した。
- Ticket作成の再入は既存Resourceを返す。開始Intentが残る場合は再作成せず照合する。結果不明でResource IDを保存できなかった場合も、TopicまたはThread識別名・親・Bot所有者による復旧経路を追加。activate_ticketの状態不一致を成功扱いしない。
- この追加差分のTicket関連35件成功（19.474秒、`.venv-p0/p2-ticket-creation-recovery.log`）。全Python回帰は `p2-ticket-delivery-windows.log` / `p2-ticket-delivery-linux.log` で別途確定する。Linuxの初回起動はDocker daemon停止で失敗し、Docker Desktopを起動した。テスト成功とは数えない。
- P2-4の残作業: TicketのWelcome/Close通知とResource削除の残るCog操作、復旧後のWelcome整備、Adapterの実SDK境界テスト、Reaction RolesのRole補償、Suggestions配送、Lockdown所有権、正式Docsと最終全回帰。Phase 2・Goal全体の完了判定は行わない。

- 追加検証確定: Windows全246件成功（53.316秒、`.venv-p0/p2-ticket-delivery-windows.log`）、Docker起動後のLinux全246件成功（72.851秒、`p2-ticket-delivery-linux-ready.log`）、Docs build成功（9.34秒、`p2-ticket-delivery-docs.log`）。初回daemon接続失敗のログは `p2-ticket-delivery-linux.log` に残す。コード固定後の同じ差分で両OSを検証した。

### 2026-09-15 承認済みLinuxテスト・Docs build再実行

- ユーザーの再実行承認に基づき、現在の作業ツリーで2件を実行した。制限環境ではDocker接続とVite設定一時ファイルの生成が拒否されたが、昇格実行は承認され、両コマンドが完走した。
- Docs build成功（9.34秒、`.venv-p0/approved-recheck-docs.log`）。この結果は本節追記前の文書に対するもの。
- Linux Pythonは256件実行、73.926秒、失敗1件・エラー12件（`.venv-p0/approved-recheck-linux.log`）。全件成功ではない。
- エラー12件は全て `suggestion_outbox` の再作成。現行SchemaからMigration履歴だけを過去へ戻すテストFixtureが、0009で追加したテーブルを残している。失敗1件はMigration件数の期待値8に対し実際9。直前のWindowsログと同じ不整合を確認した。
- この再実行ではソースやMigrationを修正していない。次の検証作業は過去Schema FixtureとMigration件数の期待値を整備し、データ保持の検証を維持したうえで両OSを再確認すること。P2-4・Phase 2・全体の完了とは判定しない。

### 2026-09-16 P2-4 Discord Adapter集約・ローカル完了

- 完了範囲はP2-4。Moderation、Ticket、Reaction Roles、Social、SuggestionsのService/Port/Discord Adapterを分離し、Interaction応答はCogに維持した。ServiceのSDK/HTTP Framework依存、Cogの外部Discord操作、Repository外SQLを検出する構造テストを追加した。
- TicketのWelcome/Staff通知/Close DM・Log/Open Mention除去をOutboxへ移した。Resource有効化とWelcome予約、CloseとResource削除・通知予約は同じTransaction。通知はTranscript ID・理由・配送Keyを保持する。Panelの不明な投稿結果は削除後も照合し、`delete_uncertain` 中の編集は409で拒否する。
- Ticket Claimは変更前後の権限と開始Intentを保存し、Claim確定と完了Receiptを同じTransactionにした。復旧はrevisionや担当者の偶然の一致で成功と判定せずReceiptを確認する。実行中処理と起動時補償は同じLeaseを共有する。
- Reaction RolesはRole変更のIntent、Assignment/Binding/期限/リアクション除去予約/完了記録を整理した。失敗時は補償し、補償失敗を保持する。通常変更・起動時復旧・期限解除はGuild/Member単位のLeaseを共有する。復元対象の最新監査ログが当該Bot Operationでない場合や証拠不足時は、人手変更を上書きしない。
- Suggestionsは0009の専用Outboxを共通Runnerへ接続した。作成・投票・審査と予約を同じTransactionにし、送信Intent/投稿ID保存はQueue Tokenと期限を検査する。投稿後DB失敗は識別印で照合し、参照競合は成功扱いしない。復旧後の表示更新も予約する。共通Queueは計8種類。
- Social/Reaction Rolesでは投稿照合中の403も結果不明として保持する。SocialのChannel取得不能は再試行対象にし、既存の不明配送を未送信に戻さない。投稿識別印はBot作者と照合し、Reaction Rolesでは設定IDと作成日時を組にする。
- 0010にResource Lease表を追加。SQLと所有権検査は `jobs/repository.py`、非同期更新・中断・解放は `jobs/leases.py`。取得ごとのToken、有効期限、Heartbeat失敗時の中断、旧所有者による確定・更新・後継Lease削除の拒否を検証した。
- Lockdownは全復元情報をAPI前に保存し、開始/手動復元/期限復元をGuild単位で排他する。競合・権限喪失・DB失敗はactiveとエラーを残す。完了と対応Raid解除は同じTransaction。別のRaid無信号処理も、未復元Lockdownや更新済みシグナルを無視して解除しない。
- ModerationのUnban・反応対象Message取得をAdapterへ移し、UnbanのCase記録もServiceへ統一した。Safetyの権限確認呼出しと、AutoModの入力変換関数を同名ローカル変数で隠す不具合を修正し、実行経路をテストした。
- 旧版Migration Fixtureは0009の新設表も除去してから履歴を戻す形へ修正した。空の新設表と採番情報を明示的に期待し、既存データ比較を維持した。別テストでは0001〜0008だけを適用した実Schemaから0009/0010へ更新し、全既存行・提案・投票・履歴、照合専用Backfill、再適用を検証した。
- 途中回帰: 256件の失敗1/エラー12を修正。その後264件でRepository外SQLが1件失敗し配置を修正。270件では両OSでテスト用Reaction Role設定のcreated_at欠落が1件失敗し、現行設定と同じFixtureへ修正した。これらの失敗を成功件数には含めない。
- 最終固定コードのWindows全272件成功（68.022秒、`.venv-p0/p2-adapter-verified-windows.log`）、Linuxコンテナ全272件成功（128.386秒、`p2-adapter-verified-linux.log`）。正式Architecture/Migration資料のDocs build成功（6.64秒、`p2-adapter-docs.log`）。その後のPython変更は末尾空行の除去のみ。Frontend変更なし。
- 実行計画の現在地と本節の引継ぎを含めたDocs最終buildも成功（5.26秒、`.venv-p0/p2-adapter-docs-final.log`）。build後の追記はこの結果記録のみ。
- 保全検証: 0009適用済み `data/backups/p2-adapters-0915/verified.sqlite3` を新規複製し、`data/backups/p2-adapters-0916/verified.sqlite3` に0010を適用した。既存66表98行の全値保持、原複製不変、integrity_check=ok、FK違反0、再適用差分なしを確認。原運用DBを変更していない。0001〜0008の差分なし。0009/0010も以後改変せず、次のSchema番号は0011。
- 次はP2-5。`dashboard/api_v1.py` の公開Contract/認可境界を固定してDomain Routerへ分割する。P2-6、Phase 3〜5は未着手。Phase 2全体・Goal全体・Stageリリースは未完了。
- 実Discord/OAuth/Webhook、遠隔本番DB適用、実Transcript/S3復元は未実施ゲートとして維持する。不明な投稿や補償の証拠不足は監査記録とResourceの人手照合が必要であり、ローカルテスト成功を実機運用の完了とは扱わない。

### 2026-09-16 承認済みLinuxテスト・Docs build再実行

- 使用量上限解消後の再実行承認に基づき、P2-5作業中の現在の作業ツリーを検証した。検証中のソース変更は行っていない。
- LinuxコンテナのPython全277件成功（100.666秒）。ネットワーク無効・作業ツリーの読み取り専用Mountで実行。ログ: `.venv-p0/approved-recheck-0916-linux.log`。
- Docs build成功（9.29秒）。ログ: `.venv-p0/approved-recheck-0916-docs.log`。本節の結果追記前の文書を検証した。
- この再実行ではソース・Migrationを変更していない。P2-5の途中検証であり、P2-5・Phase 2・全体・Stageの完了とは判定しない。


### 2026-09-16 P2-5 Domain API Router・共通Dependency

- 分割前のOpenAPI 59パス、認証・認可・CSRF応答199ケースを `tests/fixtures/api_v1_contract.json` へ固定した。分割前5件成功を確認し、分割後も同一Fixtureで公開URL・パラメータ・HTTP応答を比較した。Fixtureを分割後実装に合わせて更新していない。
- `dashboard/api_v1.py` をContext生成と9 Routerの合成へ縮小。`dashboard/api/` にSession、Guild、Modules、Suggestions、Social、Moderation、Reaction Roles、Ticket設定、Ticket操作のHTTP処理を配置した。Ticket設定とInbox/Transcript操作は異なる責務として分離した。
- `context.py` でRepository・Service・Discord APIをアプリごとに生成し、各Routerへ明示的に渡す。API ModuleのImport時のDB/設定生成や `dashboard.app` への依存を禁止する構造テストを追加。新ディレクトリもRepository外SQL禁止テストの対象に加えた。
- `dependencies.py` にサーバー側Session、Guild管理権限、CSRFを集約し、FastAPI Dependsへ接続。既存エラー順序が必要な箇所は共通メソッドを明示呼出しする。公開Social OAuth開始・公開画面のSession判定も同じ検証を利用し、HTMLエラー/Redirectは維持した。
- `resources.py` のGuild Resource IndexをModules/Suggestions/Social/Reaction Roles/Ticketで利用。Ticket固有のChannel種別・Role・Bot権限・Emoji検査は `ticket_resources.py`。表示変換はserialization、Ticket presentation、Feature presentationへ分離した。
- `ticket_dependencies.py` にStaff/担当Teamの認可を集約。更新時はGuild管理権限とTeam所属をキャッシュなしで再確認する。明示Team user IDが残っていてもGuild所属不在なら拒否し、Guild一覧にも同じ判定を適用。申請者本人のTranscript/添付閲覧権限は維持した。
- `errors.py` にHTTPエラーとrevision競合検査を集約。不正なIf-Matchは500ではなく422 `revision_invalid`、古いrevisionは409。Reaction Roles削除のHeader必須条件を維持し、引用符付き整数も受理する。失敗時に保存/削除されないことをHTTPで検証した。
- 追加検証はSocial/Moderation/Reaction Rolesの保存・再読込・競合・別Guild、Domainの異GuildResource/Bot権限不足、Ticket担当Team・所属喪失・操作直前の権限変更、暗号化Transcript/添付の本人/Staff/他ユーザー/未認証/期限切れ、Session失効、複数アプリのDB/Discord依存分離。専用Contract/構造16件成功（8.386秒、`.venv-p0/p2-api-final-focused.log`）。その後のGuild一覧共通化も以下の全回帰に含む。
- 最終コード固定後のWindows全288件成功（95.262秒、`.venv-p0/p2-api-verified-windows.log`）、Linuxコンテナ全288件成功（140.963秒、`p2-api-verified-linux.log`）。テスト実行中はPythonコードを変更せず、Docsのみ更新した。
- Frontend型検査成功（`.venv-p0/p2-api-frontend-typecheck-approved.log`）。初回はtsbuildinfo書込みのsandbox制限で停止し、承認された昇格実行で成功した。Frontendソース変更なし。今回はFrontend build/Playwrightの再実行を行っていない。
- 正式API資料のエラー例を実応答に合わせ、Architectureへファイルと責務の対応表を追加。現行の辞書SchemaやDomain別ID・日時・Pagination・fields/errorsの差は保持し、P2-6でFrontendと同時に型/制約を統一する。
- Schema/Migration追加・既存0001〜0010の改変・運用DB/保全DBへの書込みなし。最新保全複製は `data/backups/p2-adapters-0916/verified.sqlite3`、次のSchema番号0011を維持する。
- 次はP2-6。型生成・共通入力制約・共通UI・App Shell/Router・Route遅延読込・翻訳Namespace・保存/権限/競合と視覚/キーボード回帰までを一単位として進める。P2-5のDocs build結果を以下に確定する。Phase 2全体、Phase 3〜5、実Discord/OAuth/Webhook、遠隔本番DB、実Transcript/S3復元とStage判定は未完了。
- 正式Docs build成功（11.22秒、`.venv-p0/p2-api-docs-final.log`）。実行計画・API資料・Architecture・本節を含めて検証した。build後の変更は成功結果とローカル完了表示の追記のみ。P2-5はローカル完了、全体Goalは継続する。

### 2026-09-17 承認済みLinuxテスト・Docs buildの再実行

- 使用量上限解消後の再実行承認を受け、現在のP2-6作業ツリーを変更せず検証した。
- Linux固定コンテナの全Pythonテスト294件成功（150.232秒）。`docker run --rm --network none --mount type=bind,source=D:\Desktop\dev\discordBot-Tueka,target=/app,readonly tueka-test:p0 python -m unittest discover -s tests -p 'test_*.py'`。ログ: `.venv-p0/approved-recheck-0917-linux.log`。
- Docsの `npm run build` 成功（9.96秒）。ログ: `.venv-p0/approved-recheck-0917-docs.log`。最初の試行はログ出力先の相対パス誤りで起動前に失敗し、パス修正後の実行で成功した。本節追記前の文書を検証した。
- 既存ログも確認：Windows全294件成功（127.441秒、`p2-6-windows-full.log`）。画面検証は47件成功・1件失敗（`p2-ui-expanded-a11y.log`）。mobile-320の概要見出しが5秒以内に表示されなかった失敗は未解決であり、今回再実行していない。
- 本再実行ではソース・Migration・運用DB・保全DBを変更せず、Gitのステージ操作も行っていない。P2-6、Phase 2、全体、Stageの完了とは判定しない。
- 次の着手点：画面検証の失敗原因調査と修正、P2-6の残るFrontend検証・正式API/Architecture資料更新・完了条件の照合。実Discord/OAuth/Webhook、遠隔本番DB、実Transcript/S3復元の未検証ゲートは維持する。

### 2026-09-18 P2-6 型生成・共通UI・画面構造の整理

- 公開HTTP Schemaを `dashboard/api/schemas/` のDomain別Modelへ分離。`body.py` で同じ入力ModelからOpenAPIのrequestBodyと実行時検証を構築する。部分入力で省略された項目は省略のままDomainへ渡し、既定値・組合せ・Resource検証を維持した。
- `scripts/generate_api.py` は一時DBにMigrationを適用して実Routerを構築し、`dashboard/api/openapi.json` と `dashboard/frontend/src/generated/api.ts` を生成する。操作別の入力・応答型、文字数/件数/値の制約を出力。`--check` とWindows/Linux CIで生成差分を検査する。運用DB・外部接続・環境変数を生成に必要としない。
- Frontendの手書きDTOを生成型へ置換し、`request` / `encodeBody` で操作別の入出力を参照。204、Session/CSRF、項目エラー、409を共通Clientで処理する。添付はOpenAPIでoctet-stream、ClientでBlobとし、取得したバイト内容までテストした。
- APIの認証・認可・Domain・JSON/パス/Query入力エラーを `detail: {code,message,errors}` へ統一。元の59パス・199ケースのFixtureは保持し、意図した応答変換をContract比較側で明示した。公開HTML/OAuth RedirectはこのJSON契約と区別する。
- DiscordのSnowflakeは文字列、内部DB ID/revisionは整数へ統一。TicketのForm/Team/Panel/Panel Message参照とReaction RolesのLink Groupを整数にした。Moderation Case/Lockdown/イベントのDiscord IDも明示的に型付けした。日時はUnix秒、週次Scheduleはtimezoneと曜日別HH:mm、Items一覧はnextを常に返し終端/全件はnullとする。
- 最終監査でCase未作成のModerationイベントのnullがResponseValidationErrorになることをHTTPテストで再現した。case_idとReaction Roles監査の任意対象/Emoji/理由をnullableに修正し、イベント一覧と概要の両経路、19桁IDを検証した。修正前8件中1件失敗（`p2-schema-null-before.log`）、修正後8件成功・9.207秒（`p2-schema-null-after.log`）。
- `App.tsx` はSessionと最上位Routeへ縮小。appにShell/Navigation/Account/Preferences、featuresにDomain別Router・画面、routing/catalogとDomain catalogにメタデータを配置。Reaction Rolesも一覧・編集・設定・Link Groupへ分離した。RootとDomain画面をlazy/Suspenseで遅延読込みする。
- SaveBar、ResourcePicker、AccessPolicy、Field/Toggle/FormFieldsEditor、EmbedEditor、WeeklyScheduleEditor、PermissionDiagnostics、状態/項目エラー表示をcomponentsへ抽出。EmbedのTicket変数とSchedule見出しは呼出し側から渡す。保存中の破棄防止とHTML formの必須検証を維持する。
- 翻訳は日英それぞれcommon/moderation/tickets/reactionRoles/social/suggestionsへ分割。複数Namespaceのfallbackを設定し、抽出後に未翻訳キーが表示される問題を修正した。翻訳ファイルは初期登録、画面モジュールは遅延読込みとして区別する。
- 初回の画面検証失敗は、開発サーバーの遅延モジュール配信に約3秒を要し、5秒の見出し待ちを超えたTraceを確認。Playwrightを専用一時出力先にbuildしたSPAのpreviewへ変更した。本番/UIのbuild先を上書きしない。変更後48件成功を確認し、共通Embed/週次Scheduleの編集保存と320px長文表示の検証を追加した。
- Screenshotの目視で長い機能名と状態表示の重なりを確認し、既存Grid内の文字列折返しを修正。design.mdとtokens.cssは変更せず、視覚の再設計はしていない。概要・履歴空状態・Docs案内の固定日本語をcommon Namespaceへ移した。
- 途中検証のWindows/Linux各295件成功（225.241秒/412.096秒）はnull修正前の結果。最終296件・Frontend/Docsの結果は後続箇条書きで確定し、途中結果で完了判定しない。
- READMEと正式API/Architecture資料に生成手順、契約変更、ファイルと責務、共通UI・翻訳・遅延読込を反映。Schema/Migration追加・0001〜0010改変・運用DB/保全DBへの書込みなし。保全複製は `data/backups/p2-adapters-0916/verified.sqlite3`、次のMigration番号0011を維持する。
- 最終固定コードのWindows全296件成功（244.929秒、`.venv-p0/p2-6-complete-windows.log`）、Linux固定コンテナ全296件成功（242.970秒、`p2-6-complete-linux.log`）。nullイベント・実IDの追加回帰を含む。テスト中はPython/Migrationを変更していない。
- 型生成差分検査成功（`python scripts/generate_api.py --check`）。FrontendのTypeScript型検査を含む本番build成功（10.97秒、`p2-6-complete-frontend-build.log`）、Vitest14件成功（5.16秒、`p2-6-complete-vitest.log`）。Blob.textを持たないjsdomに合わせ、テストはFileReaderで実際の内容を検証した。
- 画面回帰48件成功（2.1分、`p2-6-complete-ui.log`）。320/375/768/1440px、日英、3外観×light/dark、保存/再読込・409/403時の入力保持・無効化・19桁ID・Keyboard・Axeを検証。TicketのEmbed/週次Schedule編集を保存Payloadまで確認した。途中の追加テストは誤ったwelcome_messageキーを参照して失敗し、実契約のwelcome_embedへ訂正した。
- 最終Screenshotを目視し、320px英語の長い機能名の折返しと768px日本語の配置を確認。画像8点は `.venv-p0/p2-6-dashboard-screenshots.zip` へ保存。画面回帰後は余分な末尾空白だけを除去し、`git diff HEAD --check` 成功。Gitのステージ/Commit操作は行っていない。
- 正式Docs build成功（11.78秒、`p2-6-docs-build.log`）、Docsの5画面幅10件成功（22.4秒、`p2-6-docs-a11y.log`）。Docsテストの対象は日本語トップとTicket長文ページ、メニュー/外観/検索入口/Accessibility。Dashboardの日英・全外観の検証と区別する。
- 判定：P2-6の計画・実装・ローカル回帰・正式資料を完了。次は下記の計画変更で追加したP2-7。Phase 2全体はP2-7が残るため未完了。Phase 3〜5、実Discord/OAuth/Webhook、PostgreSQL運用確認、実Transcript/S3復元とStageリリース判定は未完了のまま保持する。

### 2026-09-18 計画変更：PostgreSQL移行と開発DBの扱い

- ユーザー指示によりPostgreSQL移行を必須のP2-7として追加した。順序はP2-6→P2-7→既存P3-1〜4。PostgreSQL移行をSQLiteの性能閾値超過まで待つ旧方針を撤回し、ROADMAPとEXECUTION_PLANを同時更新した。
- 原DBは破棄してよい開発段階のデータ。空PostgreSQLへの切替を採用し、SQLiteからのETL・Dual Write・無停止移行・現行開発データ保持を必須条件から外した。過去の保全検証は実施記録として保持する。今回の計画変更ではDB/Backup/Transcript/秘密情報/外部Discord Resourceを削除していない。
- P2-7の具体的な作業順：SQLite依存棚卸しと実PostgreSQLテスト基盤→接続/Pool/Migration→全Domain Repository→Queue/Lease/同時revision→Runtime/CI/型生成→開発DB切替と別DB Restore→全回帰とDocs。PostgreSQL専用初期MigrationはSQLite 0001〜0010と別履歴にする。
- Phase 3もPostgreSQL前提へ変更。DB専用Service/Volume、readiness→migrate→3Serviceの起動順、環境別接続秘密、接続待ち/lock/deadlock監視、DB論理BackupとTranscript・鍵世代を組み合わせたRestoreを計画した。当初のアプリService各1 Replicaは維持する。
- 開発DB破棄の許可は将来のStage/本番データへ拡張しない。PostgreSQLはまだ未実装であり、現Runtimeと今回のP2-6テストはSQLiteである。次の実装担当はEXECUTION_PLAN第9節を起点に、テスト用PostgreSQLと接続/Migration境界から着手する。
- 計画変更・P2-6完了記録を反映した最終Docs build成功（7.44秒、`.venv-p0/p2-6-plan-final-docs.log`）。初回は公開対象外のEXECUTION_PLANへのリンクで停止し、Repository内パスの説明へ修正して成功した。最終build後の変更はこの結果追記のみ。


### 2026-09-18 P2-7 作業中：PostgreSQL基盤とRepository移行

- P2-7は未完了。PostgreSQL 18の隔離テストServiceを起動し、psycopg 3・接続Pool・Transaction・専用Migration履歴・Checksum・Migration排他・Schema単位のテスト隔離を実装した。初期Migrationは66テーブルで、履歴テーブルを含め67テーブル。SQLiteの旧Migrationは履歴資料として保持し、原開発DBは変更していない。
- `compose.postgres-test.yaml` は専用Project `tueka-p27`、localhost:55432、tmpfsで稼働。Composeには `--env-file tests/postgres.env` を指定し、アプリの秘密情報を含む.envを補間しない。テストは明示的な `TUEKA_TEST_DATABASE_URL` と `tueka_test` で始まるDB名を要求する。
- Dashboard/GuildSettings/Community/Engagementに続き、Jobs・Social・Moderation・Suggestions・ReactionRolesをPostgreSQL SQLへ変換。採番はRETURNING、重複処理はON CONFLICT、Queue取得はFOR UPDATE SKIP LOCKED、所有権確認は行Lock、未作成Resourceの競合はTransaction Advisory Lockで保護した。
- 実PostgreSQLの `tests/test_postgres.py` は13件成功（4.384秒）。Migration初期化/再適用/失敗Rollback/排他、Schema隔離/大きなID、同時revision、Queue期限切れ引継ぎ/旧Owner拒否、Social単一Claim/OAuth一度限り、Moderationポイント同時加算/Case・Lockdown重複防止、Suggestions投票/Review/Outbox、ReactionRole設定更新/Link Group/Recoveryを確認。
- これは移行済み境界の限定テストであり、全回帰の成功を意味しない。Ticket Repository、RuntimeのDATABASE_URL切替、既存テストFixture、型生成、CI、Backup/Restore、正式Docsが残る。現時点の作業木は移行途中であり、旧SQLite設定での起動はできない。各Domainの全面回帰・競合監査も今後必要。
- GitのStage/Commit操作は実施していない。P2-7の完了判定とPhase 3への進行は保留し、EXECUTION_PLANの順序を維持する。


### 2026-09-19 P2-7 完了：PostgreSQL移行とPhase 2のローカル出口

- 判定：P2-7の計画・実装・実PostgreSQL検証・Docs更新を完了し、Phase 2のローカル出口を満たした。次は既存番号を維持してP3-1。Goal全体は未完了で、Phase 3〜5とStage実環境ゲートを残す。
- 接続境界を旧`database.py`から`database/connections.py`、`migrations.py`、`operations.py`、`testing.py`へ分割。psycopg/PoolをLockへ追加し、DATABASE_URL、接続先ごとの最大4接続、Transaction、SQL/lock/Pool待ち時間、Schema適用済み検査を共通化した。SQLite Runtime fallbackはない。
- PostgreSQL専用`migrations/postgresql/0001_initial.sql`に66テーブル・39 Index・外部キーを定義し、履歴を含め67テーブル。BIGINT/Identity、TEXT JSON、既存0/1 bool、UTC epoch秒を明示。SQLite 0001〜0010は過去の履歴として保持し、データETLは実装しない。
- 9 Domain RepositoryとJobsをnative PostgreSQLへ移行。RETURNING、ON CONFLICT、JSONB演算、集計、revision、外部キー、採番を実DBで検証した。QueueのFOR UPDATE SKIP LOCKED、Resource Leaseの行Lock、Entity単位のAdvisory Lockで競合を制御する。
- Dashboard/Guild設定・Moderation更新・Social/Reaction Roles削除のrevisionをTransaction内で確認する。Reaction Rolesの削除Outboxと設定削除は同一Transaction。HTTPの同時Rule更新は成功1件・409競合1件を確認。SocialのTarget作成/統合/削除はProvider単位のLockを共有し、同時Alias解決でもCanonical Targetを一つにする。
- 接続断、lock timeout、deadlockを実DBへ注入し、部分変更のRollback、deadlock被害側のTransaction全体Rollback、Poolの回復、無条件の自動再実行がないことを検証した。時計はアプリ側UTC epoch秒で、接続TimezoneはUTC。Host時刻同期を運用前提としてDocsへ明記した。
- DB再初期化後の外部Resource誤操作を防ぐため、Ticketの公開Panelは保存されたGuild/Channel/Messageと照合する。管理Button/Close RequestはTicketのContainerと照合し、Feedbackは保存済み通知Messageと照合する。旧IDが新DBで再利用されても旧投稿を現在のResourceとして扱わない。
- 全Runtime入口・Cog・Service・API ContextをDATABASE_URLへ統一。型生成も一時PostgreSQL Schemaを使用し確実に削除する。既存テストFixtureは明示的なcleanup付きSchemaへ置換。旧SQLite→SQLite移行専用テストは現行のnative Migration・起動拒否・データ保持・Rollbackテストへ整理し、現行Command/古いButton拒否の回帰は残した。テストはアプリDBを流用しない。
- 最終Windows全298件成功（227.033秒、`.venv-p0/p2-7-accepted-windows.log`）、Linux/Python 3.13全298件成功（153.470秒、`p2-7-accepted-linux.log`）。Linux Imageは`tueka-test:p27`、Buildログは`p2-7-accepted-linux-build.log`。全件実行でskipなし。
- Frontend単体14件成功（5.92秒、`p2-7-vitest.log`）、TypeScript＋本番build成功（Vite 7.16秒、`p2-7-frontend-build.log`）、Dashboard画面回帰48件成功（2.5分、`p2-7-ui.log`）。日英・外観・4画面幅・保存/再読込・競合・権限・Keyboardを既存シナリオで確認した。
- 正式Docs build成功（13.96秒、`p2-7-accepted-docs-build.log`）、Docsの5画面幅10件成功（42.8秒、`p2-7-docs-a11y.log`）。Migration・Backup/Restore・環境変数・Architecture・日英の開始手順・各機能説明を更新した。OpenAPI/TypeScript生成`--check`、pip check、git diff HEAD --checkも成功。Runtime Python117ファイルを構文検査し、SQLite import/BEGIN IMMEDIATE/lastrowid/旧INSERT/旧環境変数の依存なしを確認した。
- 実pg_dump/pg_restoreは`scripts/verify_postgres_restore.py`で検証。専用Server上に今回だけのUUID付きDBを作成し、67テーブル、設定、19桁ID、採番の継続、Queue再取得、Transcript/S3オブジェクト参照、破損dump失敗時の空DB維持を確認して全検証DBを削除した。ログは`p2-7-restore-proof.log`（dump 143216 bytes）。実S3オブジェクト取得や本番暗号鍵による復号の成功を意味しない。
- 開発用`compose.postgres-dev.yaml`を追加。既存アプリProcessと同名Volumeがないことを確認し、新規`tueka-dev_postgres-dev-data`を作成、`tueka-dev-postgres-dev-1`をhealthyにした。localhost:55433 / DB・User`tueka_dev`へ初期Migrationを適用し、67テーブル・Domain行数0を確認した。アプリ`.env`へDATABASE_URLを設定し、DATABASE_PATHを除去。`Settings.from_env()`からこのDBと現行Schemaを確認した。
- 開発用資格情報は新規`.env.postgres-dev`に生成し、`.env`とともにGit対象外であることを確認した。秘密値は出力・記録していない。元SQLite・保全DB・鍵・Transcript・外部Discord Resourceは未変更。Bot/Dashboard/Workerの外部接続は起動していない。
- テスト用`tueka-p27-postgres-test-1`はlocalhost:55432 / tmpfs。Compose起動時は`--env-file tests/postgres.env`を使い、アプリ.envを補間しない。開発DBとは別接続先・別Project・別Volume。開発Composeの構文検査も成功。
- CIへLinux/PostgreSQL18、Windows runner同梱PostgreSQL17の互換検証、Linuxコンテナ接続、型生成、実Restoreを設定した。Windows runner仕様はGitHub公式`actions/runner-images`のWindows2025資料で確認。Remote Workflowは未実行で、CIが実際にgreenという主張はしない。
- Stageの実Discord/OAuth/Webhook、Stage/本番の同一digest、実Transcript/S3・鍵世代を組み合わせた復元は未完了。P3-1はSPA/Docsを含む同一Image、非root/read-only、Bot/Dashboard/Worker/Migrate/Testのコマンド境界から開始する。Git Stage/Commit操作は実施していない。ユーザーのStage変更を維持する。

### 2026-09-19 P3-1 完了：同一本番Imageと実行境界

- 判定：P3-1の計画・実装・ローカル検証・運用Docsを完了。次はP3-2。Phase 3全体、Phase 4〜5、実Stageの受入は未完了。
- Dockerfileを追加。digest固定のNode 24 stageでnpm ciからSPA/Docsを構築、Python 3.13 builderでhash付きrequirements.lockを導入し、Runtimeへ仮想環境と成果物をコピーする。RuntimeはUID/GID 10001、Node/npm/gitを含まない。アプリディレクトリを明示してCOPYし、.dockerignoreへIDE/Agentの作業用ディレクトリも追加した。
- runtime/にCommand Dispatcherとasyncio Lifecycleを配置し、bot/dashboard/social-worker/migrate/testを同じImageで実行する。Dispatcherはexecでプロセスを置換し、未知のCommandは終了コード2。BotとWorkerはSIGTERMを受けてTaskをCancelし、HTTP/Discord ClientとDB Poolを閉じる。DashboardはUvicornの終了処理を使う。
- Runtimeは起動オプションでread-only、no-new-privileges、cap-drop ALLを適用する。書込みは/tmpと/dataへ限定。/dataはTranscript等の永続Volume用で所有者10001:10001。P3-2で環境別Composeへこの契約を固定する。
- 同一Imageで全Pythonテストを行うためtests/Fixture、Docs原稿、Frontendソースを含める。Python依存は共通Lock。Node単体/画面テストは既存Dockerfile.web-testへ分離し、本番RuntimeへNodeを導入しない。
- 最終Image tueka:p31でPython全302件成功、118.970秒、skipなし（.venv-p0/p3-1-accepted-tests.log）。非root/read-only/権限昇格禁止/Capability除去、専用PostgreSQL接続、/tmp tmpfsで実行。Bot全Cogの起動/再起動、Schema未適用時の起動拒否も既存回帰に含む。Windowsは変更したDispatcher/Lifecycleの4件が成功。
- scripts/verify_runtime_image.pyで一時SchemaへのMigrationと再適用、Dashboardの実HTTP配信（SPA/Docs日本語・英語/assets）、Worker Heartbeat、実UID/NoNewPrivs、Root FSの書込み拒否、秘密設定/ローカルDB/IDE資材/Node/npm/gitの不在を確認。Dashboard/Workerはdocker stopで終了コード0。検証用コンテナとSchemaはfinallyで削除（p3-1-accepted-smoke.log）。アプリDBや実Discord資格情報は使用しない。
- 初回ビルドはVitePressの最終更新処理に必要なgitが不足し失敗、web stageだけに追加して解消。初回HTTP smokeはテストTokenでDiscord APIへ問い合わせるトップページを選んで401となったため、外部接続を必要としないSPA routeへ変更。初回終了検証でWorkerがSIGTERMを無視し137で強制停止された問題を検出し、共通Lifecycleと回帰テストを追加して終了コード0を再検証した。
- 最終Image build成功（p3-1-accepted-build.log）、内部Frontend build 6.14秒、Docs build 10.15秒。検証Imageのローカルmanifest digestはsha256:bb91303e999c94d0e0be9e910c4c748e28d9da8b29d05a8342458cc815c90dda。Registryへpushしておらず、Stage/本番同一digestの運用実績ではない。今回の完了記録はこの検証後に追記した。
- docs/operations/container.mdへ構築・5 Command・書込み先・権限・テスト資材・検証手順を記載し、Docs navigationへ追加。deploy/README.mdの古いmigrate_json.py手順も現在のPostgreSQL Migration/Lock導入へ訂正した。
- CIへruntime-image Jobを追加し、同一本番Imageのbuild・隔離起動検証・read-only全回帰を設定した。Remote Workflowは未実行。git diff --checkと変更Python構文検査が成功。Git Stage/Commit操作は実施していない。
- 引継ぎ：P3-2はdev/stage/prod Compose、PostgreSQL/Transcriptの別Volume、環境別秘密情報/Network/Project、DB readiness→migrate成功→3Service起動、DevのみSource/Vite/reloadを実装する。Imageの起動権限制約をComposeで固定する。実Discord/OAuth/Webhook、実環境同一digest、実Transcript/S3/鍵を含む復元の証拠は今後のゲートとして残す。
- 完了記録・ROADMAP・EXECUTION_PLAN更新後の最終Docs buildも成功（12.43秒、.venv-p0/p3-1-recorded-docs.log）。最終build後の変更はこの結果追記のみ。

### 2026-09-19 P3-2 完了：環境別ComposeとMigrationを起点とした起動

- 判定：P3-2の実装・隔離環境での受入・全回帰・運用Docsを完了。次はP3-3。Phase 3全体と実Stage/本番の受入は未完了。既存の開発DB/Volume、アプリ.env、鍵、Transcript、Discord Resourceは変更していない。
- deploy/compose.yamlに共通構成、compose.dev.yaml / compose.stage.yaml / compose.prod.yamlに差分を配置した。Project/Network/DB/Transcript Volume/秘密ファイルは環境ごとに分離。DBは内部NetworkのみでHost portを公開せず、Dashboardはlocalhostへ公開する。アプリの非root/read-only/no-new-privileges/cap-drop ALLと/tmp tmpfsを固定した。
- deploy/configuration.pyが環境専用設定の生成・検査を担当し、scripts/deploy.pyがCLI、deploy/compose.pyが実行順を担当する。initは既存ディレクトリを上書きせず、DB/Sessionの乱数と設定雛形を生成する。Image/Project/DB名・Role・接続先・password・OAuth Originを検査し、Stage/本番はsha256の固定参照を必須にした。秘密ファイルはGit/build contextから除外する。
- PostgreSQL初期化では管理者とは別のアプリRole/DBを作成する。アプリRoleにsuperuser/createdb/createroleを付けない。秘密ファイルはHost側の保護ディレクトリ内で管理し、Compose file secretとして個別にmountする。これはSwarm Secretの暗号化保管ではない。WindowsのACL要件とLF/改行なしのpassword保存をDocsへ記載した。
- runtime/environment.pyへ明示した秘密ファイルの読込みを集約し、Config/Migration/DB Inventoryへ適用。TUEKA_ENV_FILEがあればソース.envへfallbackせず、変数展開を行わない。既に注入済みの環境変数を上書きしない。
- upはImage/設定を検査してから旧Writerを停止し、DB readiness→今回のmigrate→終了成功→3Serviceの順で起動する。成功済みmigrateも毎回作り直す。失敗時はWriterを停止したままにし、修正後の再実行で復旧する。通常CLIにVolume削除を設けていない。資格情報が欠けてもstop/statusの対象Projectを選べるよう、設定メタデータと秘密値の検査を分けた。
- 本番昇格はStage/本番の同一固定Image、異なるDiscord Token/Client ID/Client Secret/Session Secret/callback、Stageで起動中の3Serviceの実Image IDを照合する。現在のlauncherは同一Docker Hostでの照合を対象とし、遠隔Host昇格は未実施。ローカルImage IDでの受入を、Registry公開/実Stageの機能受入と区別する。
- Devだけ必要なソースを個別にread-only mountし、Repository全体/.env/dataはmountしない。Uvicorn reloadとWatchFiles polling、非rootのNode development target、独立node_modules Volume、ViteからAPI/OAuth等への同一Origin proxyを用意した。SPA/Docs成果物を/opt/tueka-assetsへ移し、Source mountで隠れないようにした。
- TranscriptStorageのコンストラクタによるmkdirを除去し、保存時だけディレクトリを作成する。これにより空VolumeでBotよりDashboardが先に起動しても、読取り専用Volumeへの書込みで失敗しない。暗号化保存後にmkdirを拒否したReaderから復号できる回帰を追加した。
- 実検証でtmpfsのYAML flow sequence内のカンマ、Windows CRLFのDB password混入、テスト表のOwner、Dashboardの起動時mkdir、古い生成済みvite.config.jsの優先読込みを検出・修正した。Vite/Vitest/Playwrightは正本vite.config.tsを明示し、生成済みconfig.js/d.tsはImageへコピーしない。既存のHost生成物は削除していない。
- scripts/verify_compose.pyの最終受入成功（.venv-p0/p3-2-final-compose.log）。UUID付き専用dev/stage/prod Projectで空Volume導入、権限を絞ったDB Role、同一Image ID、秘密値/Network/Volume分離、DBとTranscriptの再起動後保持、Dashboardの読取り専用アクセス、Schema更新、途中失敗Rollback/全Writer停止/再実行復旧、Vite SPA/API proxy、Source変更による実reloadを確認した。テスト専用の0002/0003 Migrationは一時ディレクトリにだけ作成し、正規Migrationは変更していない。
- Compose検証BotはImage内の全Cogを読み込むoffline fixtureで、Discord Login/Command同期は行わない。検証に使った全Project/Volume/Networkと一時ファイルをfinallyで削除した。削除対象は今回生成したUUID付きProjectに限定する。実Guild/OAuth/Webhookの成功とは扱わない。
- 最終Image tueka:p32のbuild成功（p3-2-final-build.log）。Image ID sha256:87d6a6a88c0757acabfc27cb6a9165959912c10cca06f86daaf08b94560afc1f、ローカルmanifest digest sha256:e4ffdeac67402cc5a2f52390fdfed022423135bc11fbfb5f46391334d231fcd5。Registryへpushしていない。Runtime smokeも非root/read-only/NoNewPrivs、SPA/Docs/assets、Migration再適用、Heartbeat、終了コード0を確認（p3-2-final-smoke.log）。
- 最終Python全回帰：Linuxの同一本番Imageで315件成功、273.056秒（p3-2-final-linux.log）。Windows/Python 3.13で315件成功、393.994秒（p3-2-final-windows.log）。skipなし。新規検証は設定/昇格/起動失敗の12件とTranscript Readerの1件。前段313件の結果ではなく、この最終315件を基準とする。
- Frontend単体14件成功、5.98秒（p3-2-vitest.log）。画面回帰48件成功、2.2分（p3-2-ui.log）。ImageのNode stageはLockからTypeScript/SPA/Docsを構築する。CI runtime-image JobにもCompose受入を追加したが、Remote Workflowは未実行。
- 運用手順はdocs/operations/compose.md。Image手順、環境変数Reference、Docs navigation、deploy/READMEも更新した。Git Stage/Commit操作は実施していない。.env.exampleにはユーザー側の変更があるため保持し、その差分を除外したgit diff --checkが成功した。
- 引継ぎ：P3-3はDashboard liveness/readiness、Bot/Worker Heartbeat、Outbox最古滞留、PostgreSQL接続待ち/lock/deadlock、構造化LogとResource/ログ上限を実装し、Worker停止や配送/DB障害を注入して検知を確認する。運用閾値は実Stage計測から確定する。P3-4の実Transcript/S3/鍵世代を含む復元とRollback、Phase 4〜5は今後の作業として維持する。
- 完了記録・計画・運用手順を反映した最終Docs buildも成功（12.54秒、.venv-p0/p3-2-recorded-docs.log）。最終build後の変更はこの結果追記のみ。ユーザーによるStage操作を検出したが、Indexは変更していない。

### 2026-09-19 P3-3 完了：Health・Heartbeat・DB/Queue監視

- 判定：P3-3の実装・ローカル回帰・障害注入・運用Docsを完了。次はP3-4。Stage実測の通知閾値は未確定であり、Phase 3全体とGoal全体を完了扱いしない。
- observability/にHTTP入口、数値Registry、集計Repository、Heartbeat、Prometheus出力、JSONログ、共通閾値を分離した。database/jobsは軽量metricsだけを参照する。8 Queueの列対応をjobs/catalog.pyへまとめ、各Domainと監視で共有する。構造と依存方向をarchitecture.mdへ追記した。
- /health/liveはDB/資産に依存しないasync応答。/health/readyはPool接続、全MigrationのVersion/Checksum、SPA/Docs資産を検査する。/internal/metricsは32文字以上の専用MONITORING_TOKENで保護し、不成立404、DB取得失敗503。OpenAPIの既存公開契約は維持する。
- Bot・Dashboard・Social Workerは5秒ごとにHeartbeat/数値を送信。BotはGateway readinessも判定し、停止時はfalseを保存。0002_observability.sqlで起動Instance別のruntime_heartbeatsを追加。DB時刻を小数epochで保存し、同じ秒の再起動を識別する。古い観測は1日で削除。ファイルprobeはPID/ready/30秒TTLを確認し、Windowsでは危険なos.kill(pid,0)を使わない。
- HTTP件数/所要時間、Provider失敗、Queue確定結果、期限超過最古Job、Dead Letter、失効Lease、Pool使用/待ち/接続失敗、DB例外分類、pg_stat_activityの同Role lock待ち、pg_stat_databaseのdeadlockを公開。本文・個別ID・URL/query・資格情報をMetricへ入れず、Registryは系列数を制限する。未来Scheduleを遅延として誤検出しない。
- HTTPとCLIで閾値を共通化。Heartbeat 30秒/Queue 300秒は初期値で、Stage計測済み値ではない。scripts/deploy.py healthは対象環境の一時コンテナから集計JSONと終了コードを返す。収集器の接続失敗、Counter再起動Reset、最大約5秒の観測遅延、DB停止時の集計不可を運用Docsへ明記した。
- アプリログを許可したJSON項目だけに限定し、raw message/arguments/exception text/SQL/URLを除外。例外型とコード位置を残す。Uvicorn既定access logを無効化。Composeはアプリ/PGにCPU 1、768 MiB、PID 128、ログ10 MiB×3、Dev Viteは1 GiB。PGのSQL/パラメータログを抑制。Nginx sampleはqueryを含まないaccess logと/internal/遮断を追加。実Host Nginx/TLS変更・logrotate設定は行っていない。
- Windows/Python 3.13の最終全328件成功、223.317秒（.venv-p0/p3-3-final-windows.log）。同一本番ImageのLinux全328件成功、159.600秒（p3-3-linux.log）。skipなし。新規監視12件、0001→0002保持/再適用1件を追加し、既存deadlockテストでプロセス/PG Counter増加も検証した。前段Windows326件の結果は最終判定に使わない。
- Compose受入は初回にdev/stage/prod全構成を成功（p3-3-compose.log）。最終Imageでもstage/prodと障害検知を再実行し成功（p3-3-final-compose.log、--skip-dev）。Worker停止、配送失敗、DB停止でlive200/ready503、復旧後全Heartbeat正常、メトリクス認証、秘密データ不在、実Resource上限を確認した。Dev Source reloadはログ文字列ではなくDashboard実PIDの変更で検証する。検証Project/Volumeはfinallyで削除。
- Runtime smokeは非root/read-only/NoNewPrivs、実SPA/Docs/assets、Migration再適用、Heartbeat、正常終了を成功（p3-3-smoke.log）。最初の呼出しは必須--network不足で実行前終了2となり、明示ネットワークを追加して成功した。初期監視テストでscheduled_moderation_actionsにcreated_atがない問題を検出し、QueueSpecの列契約で解決した。
- 実pg_dump/pg_restoreで68表、大きなID、採番、設定、Queue、Transcript参照、破損dumpのRollbackを確認（p3-3-restore.log）。実開発DBは既存接続0を確認し、data/backups/p3-observability-0919.dumpを取得してから0002を適用。再適用0件とrequire_current成功（p3-3-dev-migrate.log）。原SQLite、既存鍵/Transcript、Discord Resourceは変更していない。Bot/Dashboard/Workerの実外部接続も起動していない。
- 最終候補Image tueka:p33のbuild成功（p3-3-final-build.log）。Image ID sha256:721624a02e3d4883d8959a2722df2c239a813002dcda3bc434319e5a6e73511f、ローカルmanifest digest sha256:e2557003f4051dd83ca141691a44ebea6b53d6dc8fecd6d002b01dbdefcf6f9b。内部SPA build 4.42秒、Docs build 6.07秒。Registry配布は未実行。以後の変更は構造説明・計画・作業記録の文書だけ。
- docs/operations/monitoring.md、環境変数Reference、運用indexとnavigationを整備。既存CIの全Python/Compose経路が監視検証を実行する。Remote Workflowは未実行。Frontendコード変更はなく、今回の画面回帰/Vitest再実行は行わない。P3-2の14件/48件を今回実行済みとは扱わない。Git Stage/Commit操作は行っていない。
- 引継ぎ：P3-4は環境別のone-shot Backup/Restore、別VolumeでDBとTranscript/鍵世代の復元・復号、保留処理の安全な再開、Snapshotと対応ImageによるRollbackを実演する。0001/0002は検証・開発DBへ適用済みなので書き換えず、以後のSchema変更は0003から追加する。実S3/Stage資格情報の確認は別ゲートとして扱う。
- 完了記録・構造説明・計画を反映した最終Docs build成功、12.69秒（.venv-p0/p3-3-recorded-docs.log）。git diff --checkも成功。最終build後の変更はこの結果追記のみ。

### 2026-09-19 P3-4 ローカル完了：復旧セット・別Volume復元・Snapshot Rollback

- 判定：P3-4の実装、ローカルの実DB/Volume受入、回帰、運用手順を完了。Phase 3の実運用出口は未完了。ユーザーはStage設定/Guild/Registry/Hostが未準備と回答し、「ローカル検証と実機受入手順の整備まで進める」と指定した。実Stageへの接続、送信、配布、Host設定変更は行わない。
- recovery/に暗号化BlobのArchive、参照/鍵/Hash/復号検証、one-shot CLIを配置。deploy/recovery.pyは停止・Snapshot・別Project復元・起動保留/解放/中止を調整し、scripts/recovery.pyを運用入口にした。PostgreSQL Clientは専用recovery-db Serviceで公式PostgreSQL 18 Imageを使用し、アプリImageへ追加しない。recovery-dataは対応アプリImage/非root/read-onlyとTranscript Volumeを使用する。
- Backupは3Writerを停止し、接続残存を拒否してDB dumpとready状態のTranscript/添付を保存する。既存宛先は上書きせず、完成時だけmanifest.jsonを作成。Image ID/参照、環境/Project、Discord Application ID、Migration、Queue集計、鍵世代指紋、Artifact SHA-256を記録する。資格情報・鍵そのものは含めない。セット全体は暗号化していないため、私有ディレクトリ/ACLとHost外保管時の暗号化が必要。参照なし/削除済みBlobは保存対象外。
- S3参照は実Object取得を必須にし、取得した暗号文を復号/内容Hash検証してセットへ保存する。失敗をローカルfallbackで隠さない。復元は全Blobを新しいlocal Volumeへ置き、復号成功後にDB backendをlocalへ変更する。復元時のTICKET_S3_BUCKET設定を拒否し、元S3へ書込み/削除しない。S3通信は単体テストでMockし、実S3の受入は未実施。
- Restoreは同じ環境/Discord Application/鍵世代/対応Image、別Project、空DB/Transcript先を要求する。DBはpg_restoreの単一Transaction。全参照Blob、Ticket回答/Message/Feedback、Social Token暗号文を復号検査し、MigrationとQueue状態を照合する。古いHeartbeatだけを除去し、Queueの試行数/Lease/Receipt/配送開始フラグは維持する。
- 元設定にrecovery-fence.json、復元先にrecovery-pending.jsonを残し、通常upを拒否。release --reconciledは外部副作用照合済みの明示後に再検証し、解放記録を保存する。自動Discord操作/自動起動は行わない。abortは失敗した復元先を起動禁止に保ち、元環境のfenceだけを解放する。部分データやVolumeを自動削除しない。Host喪失時の--source-fencedは操作者による旧Writer隔離済みの明示であり、自動隔離機能ではない。
- deploy/locking.pyで通常upとBackup/Restore/解放/中止の排他を共有。可変Source mountを持つDevを、Imageと一致する復旧セットの対象と偽らないよう拒否する。開発DBの単体Backup CLIは従来どおり使用可能。設定複製やDocker直接操作はこの制御を迂回するため運用手順で禁止する。
- deploy/tueka-backup.service/.timerを追加。専用運用アカウント、絶対パス、毎日04:00の停止時間帯をHostごとに調整して使う。--backup-rootは時刻/UUID付き宛先を作り、--resume-sourceは成功後に元々稼働していたServiceだけを再開する。今回Timerは登録・有効化していない。保持世代削除も自動化しない。
- scripts/verify_recovery.pyの最終受入成功（.venv-p0/p3-4-final-recovery.log）。UUID付きsource/restored/failedの専用Stage Projectで、Backup成功後の元Service再開、別DB/Transcript named volume、暗号化Transcript/添付2件とTicket回答/Social Token3値の復号、Checksum不一致拒否、ネイティブpg_restore失敗時の空DB保持、abort後の復元先起動禁止を確認した。
- 同じ受入で検証用0003を含む実際に異なる新Imageを構築し、元ProjectをSchema 3へ更新。Snapshotの旧Image/Schema 2へ別Projectで戻し、元DBの更新後データを保全したまま旧状態と3Serviceの正常起動を確認した。検証用0003は一時Imageにのみ存在し、正規Migrationは0001/0002のまま。
- 復元後、実Suggestions Repository/Service/共通Runnerを使い、保存済みmessage_id=111を保持し、配送不明Jobはrecover=Trueで外部Receipt Portの既存message_id=222と照合。公開後syncまで完了し、2回目のBatchは0件、公開Port呼出しは1回を確認した。Discord PortはオフラインFixtureであり実Guildへ送信していない。
- Windows全335件成功、565.050秒（p3-4-windows.log）。Linux全335件成功、381.534秒（p3-4-linux.log）。skipなし。最後にDevの可変Source拒否を1件追加し、現行復旧境界8件をWindows 6.541秒/Linux 3.446秒で再検証した（p3-4-final-boundary-windows.log / p3-4-final-boundary-linux.log）。現行のテスト総数は336だが、全336件を一回のコマンドで再実行したとは記録しない。更新排他を含むDeployment12件も成功（p3-4-deployment.log）。
- 通常Compose受入もstage/prod・環境分離・Migration失敗・監視/DB復旧が成功（p3-4-compose.log、--skip-dev）。DevのImage Snapshotは意図的に対象外とした。Frontendコードは変更しておらず、画面/Vitestを再実行したとは扱わない。CI runtime-image Jobへ復旧/旧Image Rollback受入を追加したが、Remote Workflowは未実行。
- 初期検証ではDockerfileのFROMに裸のImage IDを指定した問題、Suggestions公開後syncを考慮しないFixture、Mounts配列順に依存したVolume検査を検出。専用ローカルTag、実Queue遷移、Destination指定で修正して最終受入を成功させた。最終検証のProject/Volume/Network/派生Imageは今回のUUID対象だけを後始末した。
- 最終Image tueka:p34はp3-4-release-build.logでbuild成功。Image ID sha256:df52059331e4232e25b357593b138056b23fe5096791d62d7e71b8adb2d372a1、ローカルmanifest digest sha256:023f1b1577aad27162290649bc41da0b72b3e6ddc384d416a5d8044836f5e7fd。内部SPA build 10.01秒/Docs 11.79秒。最終境界8件と最終復旧受入はこのImageで実行。Linux全335件は直前Image（6336f51a...）で実行し、その後の変更はDev拒否ガード/対応テストとDocsに限定。Registryへpushしていない。
- Backup/Restore・更新/Rollback・Compose・構造説明を更新し、docs/operations/stage-acceptance.mdへ実機の対象固定、Gate、証拠、切戻し手順を追加。正式Docs build成功、25.00秒（p3-4-docs.log）。元開発DB/Volume/鍵/Transcript/.env/Discord Resourceはこの作業では変更していない。Git Index/Commitも操作していない。
- 引継ぎ：次はStage準備後のPhase 3実運用受入。専用設定/Guild/Registry/Host、実S3使用の有無、通知先、許容停止時間帯を確定し、stage-acceptance.mdに沿って証拠を収集する。監視閾値、実Discord/OAuth/Webhook、Registry配布、Host Nginx切替、定期Backup/通知/Host外保管は未実施。P4-1はPhase 3出口確認後。Goal全体とPhase 4〜5は未完了のまま保持する。
