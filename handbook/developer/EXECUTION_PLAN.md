# 現行実行計画

更新: 2026-09-19。方針の正本は[ROADMAP](../../ROADMAP.md)。過去の調査・完了経緯は[旧計画](history/EXECUTION_PLAN-2026-09-19.md)と[進捗](PROGRESS0910.md)へ分離する。旧P番号は履歴との対応を保つ。

状態は **未着手 / 進行中 / ローカル検証済み / 外部環境待ち / 受入完了**。コードの存在、ローカル成功、GitHub CI成功、実機受入を混同しない。

| 順序・ID | 担当 | 状態 | 依存・成果物 | 受入条件・証拠 | 阻害要因 |
| --- | --- | --- | --- | --- | --- |
| D1 役割別Docs・公開境界 | 開発者 | ローカル検証済み | 日英利用者Docs、Operator/Developer handbook、全コマンド対応表 | 日英build/リンク/検索/表示・103コマンド照合・内部資料404・Image不在 | なし |
| D2 導入・運用CLI | 開発者→運用者 | ローカル検証済み | D1。Windows/Linuxのcheck/configure/build/start、運用一覧 | クリーン設定・固定Image・失敗時停止・秘密値/Volume保持・Compose/Recovery受入 | Linux Host上の入口通し実行はC1で確認 |
| C1 最終CI確認 | 開発者 | 未着手 | D1/D2。Remote CIのRunとCommitを固定 | 全Job成功のURL/対象Commit、Linux clean checkoutでShell入口から導入。提示済み失敗ログとローカル再検証は進捗参照 | Remote最新Run未確認 |
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

## 今回のローカル証拠

[2026-09-19の進捗記録](PROGRESS0910.md)にコマンド・ログを記載。Windows/Linux Python各348件、Docsブラウザー15件、103登録コマンド照合、API型生成、クリーン導入、ComposeとRecoveryが成功。D2のローカル検証済みはWindows HostとLinuxコンテナでの確認を指し、Linux HostのShell入口を含む最終CIと実Stage受入はC1/P3-Gに残す。Remote CI Run URLの証拠はまだない。
