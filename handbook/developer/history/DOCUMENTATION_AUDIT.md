# 文書点検台帳

> 履歴資料：記録時点の調査・判断・検証証拠です。現在の作業は[開発者ガイド](../README.md)から開始してください。

点検日: 2026-09-20。対象はリポジトリのMarkdown全件（依存パッケージ・ビルド成果物・一時コピーを除く）です。履歴資料は当時の証拠として保持し、利用者・運用者の手順と区別しています。

## 点検内容

- 公開Docsと運用者資料を、操作・設定・結果を紹介する文体へ整理。日英のAutoMod、Infractions、Moderation、Reaction Roles、コマンド一覧を照合。
- cogs/engagement.pyと照合し、投票のModal説明とミニゲームのボタン説明を修正。引数・権限・結果を記載。
- compose.tools.yaml、Dockerfile、配布CLIと照合し、Host依存のテストDB手順と削除済みDockerfile参照を修正。cloneから起動までのコマンドと設定の役割を整理。
- app.env.exampleの全項目、設定ローダー、API docsの公開条件、Host Caddy、Backup/Restoreの停止・保留条件を確認。
- 運用者配下の整理前原稿をdeveloper/historyへ移動。計画の過去の詳細を保存し、ROADMAPを状態・次の作業・完了条件に整理。
- DocsのDashboardリンクを生成HTMLで照合し、VitePressのbaseが付いた `/docs/servers` からアプリの `/servers` へ修正。日英のブラウザー検査にリンク先の確認を追加。
- Suggestionsの受付待ちと配送失敗をCog・Delivery Serviceで照合。再投稿前に提案番号と配送状態を確認する手順へ修正。
- [Caddy導入](https://caddyserver.com/docs/install)、[systemd運用](https://caddyserver.com/docs/running)、[Compose補間設定](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)を公式資料と照合。

検証のコマンドと結果は[進捗](PROGRESS0910.md)へ記録します。この点検は実Stageの機能受入を表しません。

## 全文書一覧


対象: 125件。

| ファイル | 対象 | 照合先・扱い |
| --- | --- | --- |
| `deploy/README.md` | 運用者 | compose.tools.yaml、scripts/{setup,deploy,recovery}.py、deploy/ |
| `docs/dashboard/index.md` | 利用者・公開 | dashboard/frontend/src/、dashboard/api/ |
| `docs/dashboard/permissions.md` | 利用者・公開 | dashboard/frontend/src/、dashboard/api/ |
| `docs/dashboard/saving.md` | 利用者・公開 | dashboard/frontend/src/、dashboard/api/ |
| `docs/en/dashboard/index.md` | 利用者・公開 | dashboard/frontend/src/、dashboard/api/ |
| `docs/en/dashboard/permissions.md` | 利用者・公開 | dashboard/frontend/src/、dashboard/api/ |
| `docs/en/dashboard/saving.md` | 利用者・公開 | dashboard/frontend/src/、dashboard/api/ |
| `docs/en/features/anti-raid.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/en/features/anti-spam.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/en/features/audit-log.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/en/features/automod.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/en/features/autorole.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/en/features/infractions.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/en/features/leveling.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/en/features/live-stats.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/en/features/minigames.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/en/features/moderation-actions.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/en/features/moderation-logs.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/en/features/moderation.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/en/features/polls.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/en/features/reaction-roles.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/en/features/suggestions.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/en/features/temporary-voice.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/en/features/tickets.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/en/features/trust-score.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/en/features/welcome.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/en/features.md` | 利用者・公開 | Bot登録、Dashboard、Feature Registry、リンク先 |
| `docs/en/getting-started.md` | 利用者・公開 | Bot登録、Dashboard、Feature Registry、リンク先 |
| `docs/en/guide/first-server.md` | 利用者・公開 | Bot登録、Dashboard、Feature Registry、リンク先 |
| `docs/en/guide/getting-started.md` | 利用者・公開 | Bot登録、Dashboard、Feature Registry、リンク先 |
| `docs/en/guide/index.md` | 利用者・公開 | Bot登録、Dashboard、Feature Registry、リンク先 |
| `docs/en/guide/permissions.md` | 利用者・公開 | Bot登録、Dashboard、Feature Registry、リンク先 |
| `docs/en/index.md` | 利用者・公開 | Bot登録、Dashboard、Feature Registry、リンク先 |
| `docs/en/reference/commands.md` | 利用者・公開 | commands.json、cogs/、generate_commands.py |
| `docs/en/reference/glossary.md` | 利用者・公開 | Bot登録、Dashboard、Feature Registry、リンク先 |
| `docs/en/social/index.md` | 利用者・公開 | social/、cogs/social_updates.py、Dashboard Social画面 |
| `docs/en/social/instagram.md` | 利用者・公開 | social/、cogs/social_updates.py、Dashboard Social画面 |
| `docs/en/social/tiktok.md` | 利用者・公開 | social/、cogs/social_updates.py、Dashboard Social画面 |
| `docs/en/social/twitch.md` | 利用者・公開 | social/、cogs/social_updates.py、Dashboard Social画面 |
| `docs/en/social/x.md` | 利用者・公開 | social/、cogs/social_updates.py、Dashboard Social画面 |
| `docs/en/social/youtube.md` | 利用者・公開 | social/、cogs/social_updates.py、Dashboard Social画面 |
| `docs/en/troubleshooting/index.md` | 利用者・公開 | Bot登録、Dashboard、Feature Registry、リンク先 |
| `docs/en/troubleshooting.md` | 利用者・公開 | Bot登録、Dashboard、Feature Registry、リンク先 |
| `docs/features/anti-raid.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/features/anti-spam.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/features/audit-log.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/features/automod.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/features/autorole.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/features/infractions.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/features/leveling.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/features/live-stats.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/features/minigames.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/features/moderation-actions.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/features/moderation-logs.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/features/moderation.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/features/polls.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/features/reaction-roles.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/features/suggestions.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/features/temporary-voice.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/features/tickets.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/features/trust-score.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/features/welcome.md` | 利用者・公開 | feature_registry.py、cogs/、各Domainのモデル・Service |
| `docs/guide/first-server.md` | 利用者・公開 | Bot登録、Dashboard、Feature Registry、リンク先 |
| `docs/guide/getting-started.md` | 利用者・公開 | Bot登録、Dashboard、Feature Registry、リンク先 |
| `docs/guide/index.md` | 利用者・公開 | Bot登録、Dashboard、Feature Registry、リンク先 |
| `docs/guide/permissions.md` | 利用者・公開 | Bot登録、Dashboard、Feature Registry、リンク先 |
| `docs/index.md` | 利用者・公開 | Bot登録、Dashboard、Feature Registry、リンク先 |
| `docs/reference/commands.md` | 利用者・公開 | commands.json、cogs/、generate_commands.py |
| `docs/reference/glossary.md` | 利用者・公開 | Bot登録、Dashboard、Feature Registry、リンク先 |
| `docs/social/index.md` | 利用者・公開 | social/、cogs/social_updates.py、Dashboard Social画面 |
| `docs/social/instagram.md` | 利用者・公開 | social/、cogs/social_updates.py、Dashboard Social画面 |
| `docs/social/tiktok.md` | 利用者・公開 | social/、cogs/social_updates.py、Dashboard Social画面 |
| `docs/social/twitch.md` | 利用者・公開 | social/、cogs/social_updates.py、Dashboard Social画面 |
| `docs/social/x.md` | 利用者・公開 | social/、cogs/social_updates.py、Dashboard Social画面 |
| `docs/social/youtube.md` | 利用者・公開 | social/、cogs/social_updates.py、Dashboard Social画面 |
| `docs/troubleshooting/index.md` | 利用者・公開 | Bot登録、Dashboard、Feature Registry、リンク先 |
| `handbook/developer/api.md` | 開発者・入口 | Composeタスク、API/DB/Domain境界、実行計画と記録 |
| `handbook/developer/architecture.md` | 開発者・入口 | Composeタスク、API/DB/Domain境界、実行計画と記録 |
| `handbook/developer/design.md` | 開発者・入口 | Composeタスク、API/DB/Domain境界、実行計画と記録 |
| `handbook/developer/DOCUMENT_MAP.md` | 開発者・入口 | Composeタスク、API/DB/Domain境界、実行計画と記録 |
| `handbook/developer/DOCUMENTATION.md` | 開発者・入口 | Composeタスク、API/DB/Domain境界、実行計画と記録 |
| `handbook/developer/DOCUMENTATION_AUDIT.md` | 開発者・入口 | Composeタスク、API/DB/Domain境界、実行計画と記録 |
| `handbook/developer/EXECUTION_PLAN.md` | 開発者・入口 | Composeタスク、API/DB/Domain境界、実行計画と記録 |
| `handbook/developer/extending.md` | 開発者・入口 | Composeタスク、API/DB/Domain境界、実行計画と記録 |
| `handbook/developer/history/docs-before-role-split/legacy-english-operations.md` | 開発者・履歴 | 記録時点を保持。現行操作の入口から分離 |
| `handbook/developer/history/docs-before-role-split/legacy-mixed-pages/features-moderation.md` | 開発者・履歴 | 記録時点を保持。現行操作の入口から分離 |
| `handbook/developer/history/docs-before-role-split/legacy-mixed-pages/features-reaction-roles.md` | 開発者・履歴 | 記録時点を保持。現行操作の入口から分離 |
| `handbook/developer/history/docs-before-role-split/legacy-mixed-pages/features-tickets.md` | 開発者・履歴 | 記録時点を保持。現行操作の入口から分離 |
| `handbook/developer/history/docs-before-role-split/legacy-mixed-pages/guide-permissions.md` | 開発者・履歴 | 記録時点を保持。現行操作の入口から分離 |
| `handbook/developer/history/docs-before-role-split/legacy-mixed-pages/social-index.md` | 開発者・履歴 | 記録時点を保持。現行操作の入口から分離 |
| `handbook/developer/history/docs-before-role-split/legacy-mixed-pages/social-instagram.md` | 開発者・履歴 | 記録時点を保持。現行操作の入口から分離 |
| `handbook/developer/history/docs-before-role-split/legacy-mixed-pages/social-tiktok.md` | 開発者・履歴 | 記録時点を保持。現行操作の入口から分離 |
| `handbook/developer/history/docs-before-role-split/legacy-mixed-pages/social-twitch.md` | 開発者・履歴 | 記録時点を保持。現行操作の入口から分離 |
| `handbook/developer/history/docs-before-role-split/legacy-mixed-pages/social-x.md` | 開発者・履歴 | 記録時点を保持。現行操作の入口から分離 |
| `handbook/developer/history/docs-before-role-split/legacy-mixed-pages/social-youtube.md` | 開発者・履歴 | 記録時点を保持。現行操作の入口から分離 |
| `handbook/developer/history/docs-before-role-split/legacy-mixed-pages/troubleshooting-index.md` | 開発者・履歴 | 記録時点を保持。現行操作の入口から分離 |
| `handbook/developer/history/docs-before-role-split/README.md` | 開発者・履歴 | 記録時点を保持。現行操作の入口から分離 |
| `handbook/developer/history/EXECUTION_PLAN-2026-09-19.md` | 開発者・履歴 | 記録時点を保持。現行操作の入口から分離 |
| `handbook/developer/UNUSED_CODE_AUDIT.md` | 開発者 | 未使用資産の削除根拠と保持対象 |
| `handbook/developer/history/ROADMAP-2026-09-20.md` | 開発者・履歴 | 記録時点を保持。現行操作の入口から分離 |
| `handbook/developer/inventory/V1_INVENTORY.md` | 開発者・履歴 | 記録時点を保持。現行操作の入口から分離 |
| `handbook/developer/PROGRESS0910.md` | 開発者・履歴 | 記録時点を保持。現行操作の入口から分離 |
| `handbook/developer/README.md` | 開発者・入口 | Composeタスク、API/DB/Domain境界、実行計画と記録 |
| `handbook/developer/TESTING.md` | 開発者・入口 | Composeタスク、API/DB/Domain境界、実行計画と記録 |
| `handbook/developer/TOOLS.md` | 開発者・入口 | Composeタスク、API/DB/Domain境界、実行計画と記録 |
| `handbook/operator/application-setup.md` | 運用者 | compose.tools.yaml、scripts/{setup,deploy,recovery}.py、deploy/ |
| `handbook/operator/backup.md` | 運用者 | compose.tools.yaml、scripts/{setup,deploy,recovery}.py、deploy/ |
| `handbook/operator/caddy.md` | 運用者 | compose.tools.yaml、scripts/{setup,deploy,recovery}.py、deploy/ |
| `handbook/operator/commands.md` | 運用者 | compose.tools.yaml、scripts/{setup,deploy,recovery}.py、deploy/ |
| `handbook/operator/compose.md` | 運用者 | compose.tools.yaml、scripts/{setup,deploy,recovery}.py、deploy/ |
| `handbook/operator/container.md` | 運用者 | compose.tools.yaml、scripts/{setup,deploy,recovery}.py、deploy/ |
| `handbook/operator/environment.md` | 運用者 | compose.tools.yaml、scripts/{setup,deploy,recovery}.py、deploy/ |
| `handbook/operator/index.md` | 運用者 | compose.tools.yaml、scripts/{setup,deploy,recovery}.py、deploy/ |
| `handbook/operator/linux.md` | 運用者 | compose.tools.yaml、scripts/{setup,deploy,recovery}.py、deploy/ |
| `handbook/operator/migrations.md` | 運用者 | compose.tools.yaml、scripts/{setup,deploy,recovery}.py、deploy/ |
| `handbook/operator/monitoring.md` | 運用者 | compose.tools.yaml、scripts/{setup,deploy,recovery}.py、deploy/ |
| `handbook/operator/README.md` | 運用者 | compose.tools.yaml、scripts/{setup,deploy,recovery}.py、deploy/ |
| `handbook/operator/security.md` | 運用者 | compose.tools.yaml、scripts/{setup,deploy,recovery}.py、deploy/ |
| `handbook/operator/setup.md` | 運用者 | compose.tools.yaml、scripts/{setup,deploy,recovery}.py、deploy/ |
| `handbook/operator/stage-acceptance.md` | 運用者 | compose.tools.yaml、scripts/{setup,deploy,recovery}.py、deploy/ |
| `handbook/operator/upgrade.md` | 運用者 | compose.tools.yaml、scripts/{setup,deploy,recovery}.py、deploy/ |
| `handbook/operator/windows.md` | 運用者 | compose.tools.yaml、scripts/{setup,deploy,recovery}.py、deploy/ |
| `handbook/operator/worker.md` | 運用者 | compose.tools.yaml、scripts/{setup,deploy,recovery}.py、deploy/ |
| `README.md` | 開発者・入口 | Composeタスク、API/DB/Domain境界、実行計画と記録 |
| `ROADMAP.md` | 開発者・入口 | Composeタスク、API/DB/Domain境界、実行計画と記録 |
