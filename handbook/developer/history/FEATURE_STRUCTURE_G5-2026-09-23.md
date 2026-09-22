# G5 拡張性・境界受入（完了）

対象: `e509247` からの作業ツリー。2026-09-23 JST、Windows / Docker Desktop Linuxコンテナ。

- テスト専用機能を既存カテゴリーへ追加、新カテゴリーを登録、登録を解除する3ケースで実Registry・Settings・全Bot拡張・APIを起動。既定設定の保存/再読込、revision、CSRF、認可、起動/終了一回、解除後404を検証。Bot起動・API合成のソース変更なし。
- 実Shellで既定フォームの編集/保存、専用画面override、新カテゴリー表示、Navigation/検索/パンくず、解除後404を検証。差し替えはRegistryとHTTP応答のみ。Shellのソース変更なし。
- Python/TypeScriptの構文木でDomain→SDK/HTTP、共有基盤→機能、カテゴリー間内部Importを拒否。相対Import・再Export・動的Importの拒否例も検証し、UIでは間接依存も追跡する。
- 検査が検出した2境界を修正。Team所属判定を `ticketing/access.py` へ移し、共通SessionからTicket HTTP実装への参照を解消。Moderation/概要の権限表示は共有PermissionDiagnosticsを直接利用し、全体Registryへの逆参照を解消。判定・表示・公開契約は維持。

実行入口: `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm <task>`。以下のローカルログは閲覧確認済み。

| タスク | 結果・証拠（`artifacts/` 配下） |
| --- | --- |
| `check`（`--build`付き） | exit 0。`check/20260922T155453-8e834780` |
| `test-python` | 全405件成功。`test-python/20260922T160642-b12a25c8` |
| 登録/境界検査の最終強化 | `test-python -p test_feature_extension.py`（3ケース）と `test-python -p test_feature_boundaries.py`（3件）成功。`test-python/20260922T161020-b1808b55` / `test-python/20260922T161107-a02e7c41` |
| `test-web` | 全118件成功。`test-web/20260922T160640-1561f417` |
| `typecheck` / `build-web` | exit 0。`typecheck/20260922T160443-19b4a34c` / `build-web/20260922T160939-4b7ed7aa` |
| `test-a11y dashboard.spec.ts --grep 'shared permission diagnostics\|overview is responsive'` | 対象12件成功。日英の概要/Moderation権限表示、4画面幅・重複除去・Accessibility。`test-a11y/20260922T160641-4b5d6918` |
| `api-check` / `commands-check` | API生成物一致、103コマンド一致。`api-check/20260922T160724-121d8150` / `commands-check/20260922T160942-a82c2231` |
| `check-docs` | exit 0。`check-docs/20260922T161300-5b2488a6` |
| 差分・片付け | `git diff --check` 指摘なし。tools専用PostgreSQLを `down --remove-orphans` で停止・撤去、Volume保持 |

G5残作業なし。次はG6の旧経路整理・文書/同梱確認・全群CI・Image受入。仮機能はテスト内に限定し、実Discordへの接続は行っていない。独立Linux Host・Remote CI・実Stageは既存の別ゲートで扱う。
