# 開発者資料の整理記録 2026-09-21

対象: e807ab3からの文書・検査対象の変更。既存作業ツリーは開始時にクリーン。

- AGENTS.mdを作業指示の入口にし、設計原則、構成表、引き継ぎ、Backend/Web/基盤の作業指示を追加。
- 進捗、文書移管・点検、未使用資産点検、V1棚卸しとSchema証拠をhistoryへ移動。現行文書からのリンクを更新し、記録時点の資料であることを冒頭に明示。
- アーキテクチャの移行時点説明を現行仕様へ整理。視覚仕様を日本語で記載し、設計基準と実機受入を区別。整理前の視覚仕様はdesign-2026-09-21.mdに保存。
- 会話の設計原則、公開境界、設定、Docker、Caddy、データ保持、Stage未準備と受入証拠の扱いをリポジトリへ記録。
- check_documentation.pyの対象へAGENTS.mdを追加。

検証: `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build check-docs` 成功。最終ログは `artifacts/check-docs/20260921T050618-a4c13dab/`。`git diff --check` 成功。移転Schemaの内容一致と記録の移転を確認。

アプリ実装・公開Docsの内容は変更していない。アプリ全テスト、Remote CI、実Stageは今回再実行していない。次はHANDOFF.mdとEXECUTION_PLAN.mdに従い、共通タスクの残る受入を進める。
