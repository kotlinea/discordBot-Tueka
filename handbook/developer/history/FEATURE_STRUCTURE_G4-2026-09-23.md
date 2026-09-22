# G4 Dashboard移行（完了）

対象: `2fc2cc1` からの作業ツリー。2026-09-23 JST、Windows / Docker Desktop Linuxコンテナ。

- 24機能の画面・設定・表示情報をカテゴリー登録へ集約。Ticket/Reaction Rolesはcommunity、Suggestionsはengagement、Guild基盤はappへ移設。23移設ファイルのうち20件はimport以外同一。
- Guild/Standalone Route、Navigation、検索、パンくずをRegistryから構成。共通loaderのlazy初期化を共有し、Guild・経路ごとに入力状態を分離。設定項目、Rule初期値、Provider表示は機能側が所有する。
- G0で確認した経路不整合を解消し、24機能の既存Module URLも保持。専用保存はsettingsLoadで既存画面へ接続。Reaction Rolesの未知子経路は登録された一覧URLへ戻す。Backend/API/DB契約の変更なし。

実行入口: `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm <task>`。ログはローカルartifactsに保存、閲覧確認済み。

| 検証 | 結果・証拠 |
| --- | --- |
| `check`（`--build`付き） | exit 0。`artifacts/check/20260922T150105-b3f1846e` |
| `typecheck` / `build-web` | exit 0。`artifacts/typecheck/20260922T152903-7e27dfe2` / 最終tscを含む `artifacts/build-web/20260922T154008-9c536828` |
| `test-web` | 106件成功。72件の経路・パラメーター・404・Staff・パンくず検査を含む。`artifacts/test-web/20260922T154009-98798c94` |
| `test-a11y` | 最終80件成功（4.9分）。`artifacts/test-a11y/20260922T154336-d84fb4e9` |
| Reaction Roles最終修正 | `test-a11y dashboard.spec.ts --grep 'reaction roles overview'`、4画面幅成功。`artifacts/test-a11y/20260922T154010-ba34d3ab` |
| 差分 | `git diff --check` 指摘なし |
| `check-docs` | exit 0。`artifacts/check-docs/20260922T155108-0bfb845b` |

ブラウザーはAPI応答をモックし、日英・4画面幅、保存/再読込/無効化、401ログイン遷移、403/409/422入力保持、Staff表示、遅延読込、keyboardとAccessibilityを検証する。巡回ケースは全体上限を60秒とし、各画面の検査条件は維持した。

G4残作業なし。次段階はG5。全群CI・Image受入はG6、独立Linux Host・Remote CI・実Stageは既存の別ゲートで扱う。
