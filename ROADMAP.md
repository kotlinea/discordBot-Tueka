# Tueka 開発ロードマップ

Tuekaの基盤整備、運用受入、機能改善を進める順序と完了条件を定めます。項目ごとの担当・依存・証拠は[実行計画](handbook/developer/EXECUTION_PLAN.md)、実施記録は[進捗](handbook/developer/history/PROGRESS0910.md)を参照してください。

## 構成

- Discord Bot、Dashboard、Social Workerは共通ImageとPostgreSQLを使用します。
- 開発・テスト・導入・運用の入口は `compose.tools.yaml` です。Hostの前提はGitとLinuxコンテナ対応Docker／Composeです。
- Dev／Stage／Prodのアプリ設定は環境別app.envで管理します。
- Stage／ProdはLinux HostのCaddyでHTTPS公開し、Devはlocalhost HTTPで使用します。
- 利用者向けの日英Docsは `docs/`、運用者向けは `handbook/operator/`、開発者向けは `handbook/developer/` に配置します。

## 状態

| 範囲 | 状態 | 確認対象 |
| --- | --- | --- |
| W ドキュメント・画面文言の推敲 | ローカル検証済み | 現行資料とDashboard全体を見直し、用語と操作説明を統一。文章差分55件と関連テストを確認。[計画・結果](handbook/developer/WRITING_PLAN.md) |
| L 処理の軽量化 | ローカル検証済み | [計画](handbook/developer/PERFORMANCE_PLAN.md)の範囲完了。[測定・受入](handbook/developer/history/PERFORMANCE-2026-10-03.md)。XP・設定取得・イベント集約・Social定期処理を改善。実環境性能は未検証 |
| U 表示構造・設定操作の統一 | ローカル検証済み | U0〜U6完了。[最終受入](handbook/developer/history/FEATURE_UX_U6-2026-09-29.md)。カテゴリー・大機能・登録契約・設定操作・ルール再利用を受入 |
| Phase 0〜2 | ローカル検証済み | V2、Domain境界、PostgreSQL、API/UI契約 |
| P3-1〜4 | ローカル検証済み | Image、Compose、監視、Backup/Restore |
| D1・D2 | ローカル検証済み | 役割別Docs、導入・管理CLI |
| D3 文書点検 | ローカル検証済み | 125件の点検、日英の利用者向け表現、運用手順、リンク・検索・表示 |
| T1 Composeタスク | 進行中 | ローカル全群の項目を検証済み。別Linux Host受入が残る |
| C1 Remote CI | 未確認 | 最新Commitの全Job結果とRun URL |
| P3-G Stage受入 | 外部環境待ち | 専用Host、Guild、OAuth、Webhook、Registry、公開証明書 |
| Phase 4・5 | 未着手 | Stage受入後に機能ごとの仕様と受入を進める |
| G 機能中心の構造改善 | ローカル検証済み | G0〜G6完了。カテゴリー・機能別配置、登録/override、共有UI、最終回帰 |

ローカル成功、Remote CI成功、実Stage受入はそれぞれの証拠で判定します。Stage環境は未準備です。

## 次の作業

表示構造・設定操作の改善U0〜U6は完了しました。[最終受入](handbook/developer/history/FEATURE_UX_U6-2026-09-29.md)と[拡張手順](handbook/developer/extending.md)に結果・登録契約を残し、一時計画を終了しました。以下の実環境受入と新機能の順序は維持します。

機能中心の構造改善G0〜G6は完了しました。[最終受入の証拠](handbook/developer/history/FEATURE_STRUCTURE_G6-2026-09-23.md)と[拡張手順](handbook/developer/extending.md)を参照してください。以下の実環境受入や新機能のゲートは維持します。

1. **Docsと共通タスクの確認（ローカル検証済み）**：日英Docs、生成物、テスト、Image、Compose、Recovery、Caddyと秘密情報検査の証拠をG6に記録しました。
2. **クリーン環境・CI受入**：Windows Docker DesktopとLinuxのcheckoutで共通タスクを実行し、所有権、空白・日本語パス、並列実行、失敗からの再実行を確認します。Remote CIのCommitとRun URLを記録します。
3. **Phase 3実機受入**：Stage専用Guild、OAuth、Webhook、Registry配布、監視閾値、Backup運用、使用する場合の実S3を[受入票](handbook/operator/stage-acceptance.md)で確認します。
4. **Phase 4**：機能判定表、Moderation、Ticket、Reaction Roles、Social、Suggestions、横断UXの順に改善します。
5. **Phase 5**：以下の7機能を順番に実装・受入します。

## Phase 4の完了条件

機能ごとに設定、操作、失敗、再試行、権限不足、無効化、再起動後の復旧を確認します。API、Dashboard、Discord、日英Docsの仕様を揃え、ローカルと実Stageの証拠を記録します。

| 順序 | 機能 | 主な確認 |
| --- | --- | --- |
| P4-1 | 完成度判定 | 機能・コード・テスト・実機の対応表 |
| P4-2 | Moderation | Preview、処置、Case、取消、監査 |
| P4-3 | Ticket | Panel、受付、Claim、Close、Transcript、Feedback |
| P4-4 | Reaction Roles | 全Type、期限、Link、修復、Role階層 |
| P4-5 | Social | 対象解決、取得、配送、Preview、Retry、欠落補完 |
| P4-6 | Suggestions | 審査理由、履歴、Discussion、実装済み通知 |
| P4-7 | 横断UX | 空状態、権限、競合、復旧、日英、モバイル、キーボード |

## Phase 5の順序

1. Forms / Applications
2. Moderation Appeals / ModMail
3. Scheduled Messages / Events
4. Suggestions Roadmap
5. Starboard / Highlights
6. Giveaways / Community Events
7. Server Insights

各機能にMigration、Repository、Service、Discord/API、Dashboard、日英Docs、Retention、無効化、Backup/Restore、テストとStage受入を含めます。

## 開発・リリースの原則

- RepositoryはDB、Serviceは状態遷移、Adapterは外部操作、APIは認可と入力を担当します。
- 変更は独立して検証できる単位で進め、契約変更とリリース対象を開発者が定義します。運用者は対象Imageを配布し、監視と復旧を担当します。
- Schema変更は番号付きMigrationで管理し、空DB・更新・再適用・失敗時Rollbackを検証します。
- 更新前にDB・Transcript・対応Imageを保全し、必要な鍵世代を別途保管します。
- 本番にはStageで受入した同じImageを配布します。
- 実害のある不具合は機能の着手順序より優先します。

計画の変更経緯、P0〜P3の詳細と開発DB移行時の判断は[計画履歴](handbook/developer/history/ROADMAP-2026-09-20.md)に保存しています。
