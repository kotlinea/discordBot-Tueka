# 表示構造・設定操作の計画制定

2026-09-24、対象 `e1b47e9`、開始時の作業ツリーは変更なし。

AGENTS.mdから作業指示・現行設計とShell/Registry、サーバー設定、ModerationのUI/API/保存を確認し、専用 `goal.md` を制定した。カテゴリー→機能→操作の階層、Ticket/RRの大機能化、実データに沿う設定、ルール複製・一括有効化をU0〜U6へ分割した。複数ルール保存は既に可能であり、操作導線の不足として整理した。

今回は計画のみ。実装・API・DB・画面は変更せず、過去Gの完了状態を保持。次はU0。Windows Docker Desktop/Linuxコンテナの作業前 `check` はexit 0、証拠は `artifacts/check/20260924T132737-0860fcbf`。実画面と機能回帰は未検証。

制定後 `check-docs` はexit 0（`artifacts/check-docs/20260924T133143-1ee7c467`）。`git diff --check` は指摘なし。
