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
