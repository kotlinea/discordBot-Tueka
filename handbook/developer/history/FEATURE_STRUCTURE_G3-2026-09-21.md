# G3 Backend移行（完了）

対象: `4a0837a` からの作業ツリー。2026-09-21、Windows / Docker Desktop Linuxコンテナ。

- community→engagement→moderation→socialのCog/APIを機能別に配置。統計/一時VC、投票/ミニゲーム、Echo/計算/Diceを分離。共有Moderation実行・Social配送は一度だけ登録し、ヘルプ表示順を維持。
- 機能別設定モデルと5 Providerを明示Registryへ登録。Ticket/Reaction Rolesは設定Factoryから専用Repositoryへ接続。Workerは登録から起動し、失敗時に兄弟Taskを終了する。SQL・Transactionは維持。
- 24公開機能・103コマンド・API契約を維持。認可、revision、専用保存、同一Transaction、Lease、再起動復旧を回帰検証。旧Importは固定baselineの移設対応表だけに残る。
- 承認後に移設を反映。原本の控えはローカルの `artifacts/g3-originals/` と `artifacts/g3-model-originals/`。

| 検証（すべてexit 0） | 証拠 |
| --- | --- |
| `ci --group python`: Python401件、API、103コマンド、文書、68テーブルRestore、ツール受入 | `artifacts/ci/20260921T104126-5e91b2fa` |
| `build-image`: 本番ImageとUI/Docs構築 | `artifacts/build-image/20260921T104126-9dadfe96` |
| `verify-runtime`: 非root/read-only、Migration、Dashboard/Worker起動・正常終了、Image内401件 | `artifacts/verify-runtime/20260921T104252-227bfa7e` |
| `git diff --check` | 指摘なし |

G3残作業なし。次はG4のDashboard移行。全群CI・独立Linux Host・Remote CI・実Stageは既存の後続ゲートに残す。
