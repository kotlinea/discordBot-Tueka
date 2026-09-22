# 現行実行計画

更新: 2026-09-21。方針の正本は[ROADMAP](../../ROADMAP.md)。過去の調査・完了経緯は[旧計画](history/EXECUTION_PLAN-2026-09-19.md)と[進捗](history/PROGRESS0910.md)へ分離する。旧P番号は履歴との対応を保つ。

状態は **未着手 / 進行中 / ローカル検証済み / 外部環境待ち / 受入完了**。コードの存在、ローカル成功、GitHub CI成功、実機受入を混同しない。

| 順序・ID | 担当 | 状態 | 依存・成果物 | 受入条件・証拠 | 阻害要因 |
| --- | --- | --- | --- | --- | --- |
| G 機能中心の構造改善 | 開発者 | 進行中 | [専用計画](../../goal.md)。G0〜G4完了、次はG5 | [G4 Dashboard移行・検証](history/FEATURE_STRUCTURE_G4-2026-09-23.md)。単体106件・ブラウザー80件・型検査/本番build成功 | G4なし。G5〜G6は未着手、実環境受入はC1/P3-Gで別管理 |
| D1 役割別Docs・公開境界 | 開発者 | ローカル検証済み | 日英利用者Docs、Operator/Developer handbook、全コマンド対応表 | 日英build/リンク/検索/表示・103コマンド照合・内部資料404・Image不在 | なし |
| D3 文書の仕様・文体点検 | 開発者 | ローカル検証済み | D1。[125件の点検台帳](history/DOCUMENTATION_AUDIT.md)、編集基準、表現・リンク検査 | 日英build、103コマンド照合、Docsブラウザー15件、文書8テスト成功。証拠は進捗 | Remote CI・実StageはC1/P3-G |
| D2 導入・運用CLI | 開発者→運用者 | ローカル検証済み | D1。Windows/Linuxのcheck/configure/build/start、運用一覧 | クリーン設定・固定Image・失敗時停止・秘密値/Volume保持・Compose/Recovery受入 | Linux Host上の共通Composeタスク通し実行はC1で確認 |
| T1 Composeタスク統一 | 開発者→運用者 | 進行中 | D1/D2。compose.tools.yaml、固定tools Image、CI・手順の統一を実装済み | 個別受入・Windowsパス・Linux所有権成功。[仕様](TOOLS.md)と[証拠](history/PROGRESS0910.md) | 最終一括検証と別Linux Host受入が残る。中断履歴は進捗参照。Remote CI・実Stageは別ゲート |
| C1 最終CI確認 | 開発者 | 未着手 | D1/D2。Remote CIのRunとCommitを固定 | 全Job成功のURL/対象Commit、Linux clean checkoutで共通Composeタスクから導入。提示済み失敗ログとローカル再検証は進捗参照 | Remote最新Run未確認 |
| P3-G 実機受入 | 運用者＋開発者 | 外部環境待ち | C1。専用Stage/Guild/Registry/Hostと受入票 | Discord/OAuth/Webhook、同一digest配布、監視閾値、実Transcript、使用時のS3、TLS/定期Backup/通知/Host外保管 | Stage等未準備 |
| P4-1 完成度判定 | 開発者 | 未着手 | P3出口。機能・コード・テスト・実機の対応表 | Registry/UI/Docsの安定・改善中・利用不可が一致、未検証を安定としない | P3-G |
| P4-2 Moderation | 開発者 | 未着手 | P4-1 | Preview→処置→Case→取消→監査、権限不足から復旧 | P4-1 |
| P4-3 Ticket | 開発者 | 未着手 | P4-2 | 設定→Panel→受付→Claim→Close→Transcript→Feedback、部分失敗/再起動 | 前項 |
| P4-4 Reaction Roles | 開発者 | 未着手 | P4-3 | 全Type・期限・Link・修復、Emoji/Role消失と階層変更 | 前項 |
| P4-5 Social | 開発者 | 未着手 | P4-4 | 対象解決→取得→配送→Preview→Retry、欠落補完/初回抑止 | 前項 |
| P4-6 Suggestions | 開発者 | 未着手 | P4-5 | 理由/履歴/Discussion/実装済み通知とDashboard管理 | 前項 |
| P4-7 横断UX | 開発者 | 未着手 | P4-2〜6 | 空状態・権限・競合・復旧・日英/モバイル/keyboard・Docs、Stage証拠 | 前項 |
| P5-1 Forms/Applications | 開発者 | 未着手 | Phase 4出口。機能仕様・Migration・API・UI・日英Docs | 縦断テスト・無効化/Retention/復旧・実Stage受入の証拠 | Phase 4出口 |
| P5-2 Moderation Appeals/ModMail | 開発者 | 未着手 | P5-1。機能仕様・Migration・API・UI・日英Docs | 縦断テスト・無効化/Retention/復旧・実Stage受入の証拠 | P5-1 |
| P5-3 Scheduled Messages/Events | 開発者 | 未着手 | P5-2。機能仕様・Migration・API・UI・日英Docs | 縦断テスト・無効化/Retention/復旧・実Stage受入の証拠 | P5-2 |
| P5-4 Suggestions Roadmap | 開発者 | 未着手 | P5-3。機能仕様・Migration・API・UI・日英Docs | 縦断テスト・無効化/Retention/復旧・実Stage受入の証拠 | P5-3 |
| P5-5 Starboard/Highlights | 開発者 | 未着手 | P5-4。機能仕様・Migration・API・UI・日英Docs | 縦断テスト・無効化/Retention/復旧・実Stage受入の証拠 | P5-4 |
| P5-6 Giveaways/Community Events | 開発者 | 未着手 | P5-5。機能仕様・Migration・API・UI・日英Docs | 縦断テスト・無効化/Retention/復旧・実Stage受入の証拠 | P5-5 |
| P5-7 Server Insights | 開発者 | 未着手 | P5-6。機能仕様・Migration・API・UI・日英Docs | 縦断テスト・無効化/Retention/復旧・実Stage受入の証拠 | P5-6 |

Phase 0〜2およびP3-1〜4はローカル検証済み。PostgreSQLへのRuntime統一済みであり、旧SQLite調査やV1削除を新規の未達成作業へ戻さない。P3全体の実機出口は未完了。

P5順序: Forms/Applications → Moderation Appeals/ModMail → Scheduled Messages/Events → Suggestions Roadmap → Starboard/Highlights → Giveaways/Community Events → Server Insights。各機能にMigration、Repository/Service/Adapter、認可/revision API、日英UI/Docs、Retention・無効化・復旧、テストとStage受入を含める。

実害のある不具合は機能順序より優先する。元開発DBの破棄許可は今後のStage/本番データに適用しない。今回のDocs/導入整理では既存DB初期化、実配布、新機能実装を行わない。

## 検証証拠（実行日別）

[2026-09-19の進捗記録](history/PROGRESS0910.md)にコマンド・ログを記載。Windows/Linux Python各348件、Docsブラウザー15件、103登録コマンド照合、API型生成、クリーン導入、ComposeとRecoveryが成功。D2のローカル検証済みはWindows HostとLinuxコンテナでの確認を指し、Linux Hostの共通Composeタスクを含む最終CIと実Stage受入はC1/P3-Gに残す。Remote CI Run URLの証拠はまだない。

Host Caddyの設定生成CLI・Linux/systemd手順・内部CAによるローカルHTTPS受入を追加済み。証拠は2026-09-20の進捗記録。公開DNS・証明書取得/更新・systemd常駐/reload・実OAuth/WebhookはP3-Gの実機受入に残し、Remote CIはC1で確認する。

2026-09-20のWindows Docker Desktop/Linuxコンテナで `ci --group python`（374テスト・API・103コマンド・Docs・Restore・ツール受入）、`build-image`、`verify-runtime`（Image内374テスト）が成功。[未使用資産点検の証拠](history/UNUSED_CODE_AUDIT.md)を参照。T1の全群一括検証、別Linux Host、C1/P3-Gは未完了のままとする。開発の引き継ぎと作業別指示は[HANDOFF](HANDOFF.md)を入口にする。
