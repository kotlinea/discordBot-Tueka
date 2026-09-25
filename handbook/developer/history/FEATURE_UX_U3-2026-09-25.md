# U3 設定と共通操作

2026-09-25、Windows / Docker Desktop Linuxコンテナ。対象は `b71f99ea125257f4c786946312de1a06b18e02ec` 上の作業ツリー。開始時から存在したU3の変更を継続した。状態: **ローカル受入完了。U3残作業なし、次はU4**。

## 実施内容と受入対象

| 対象 | 契約・変更 | 確認方法 |
| --- | --- | --- |
| 全24機能の管理入口 | Metadataの設定ON/OFFと実行条件を分離。親停止、必須項目、不足権限、Resource消失を表示。Registryのresource/referencesで特殊なID参照を宣言 | configurationIssues、登録拡張・境界テスト、全Module URL、U3ブラウザー |
| 共通設定・Welcome | 元revision、dirty値、再取得との分離、失敗保持、明示破棄、保存中の入力/二重送信抑止 | welcome/settings-contract、既存features/welcomeブラウザー |
| Ticket設定・Panel編集 | 取得失敗/再試行、dirty再取得、403/409/422保持、成功後再取得。Panelのreset/importは編集対象ID/revisionを維持。detachは受付と処理結果を区別 | ticket-settings、dashboardの6タブ編集・公開、workspaces、settings-contractブラウザー |
| Ticket作成Dialog・Tag・返信・Transcript評価 | 未保存・破棄・保存中抑止・失敗表示。返信と管理操作の同時送信を抑止。作成Dialogは必要なResourceだけ取得 | 型検査、共通save/draft契約、既存Ticket画面・Staffブラウザー、ソース点検 |
| RR設定・投稿Editor・Link Group | dirty値と取得値を分離、元revision保持、破棄、失敗表示、成功後再取得。設定と公開状態を分け、修復/削除の失敗を表示 | workspacesの設定保存/別名、既存RR Editorブラウザー、共通契約テスト |
| Social | 編集中の一覧再取得で入力を維持、閉じる確認・破棄、保存中抑止。Provider未設定、宛先消失、設定値、アカウント確認済みを分離 | 5 Providerの日英保存/競合ブラウザー、U3のProvider未設定 |
| Suggestions | 専用APIの応答と再取得を基準にし、dirty値を保持。必須送信先・失敗・破棄・保存中を共通化 | suggestions UIテスト、既存ブラウザー |
| Moderation RuleEditor/List・Actions | 編集中の再取得保持、入力/送信抑止、失敗表示。逐次削除の成功IDを除き、失敗後は残りだけを元revisionで再送。親停止と有効ルール0件を別表示 | rule-list-editing、共通保存テスト、既存Moderationブラウザー、U3親停止/権限/0件 |
| 共通入口・個人設定 | Overview未取得を無効にしない。Shellの背景エラーで編集画面を捨てない。個人設定にもdraft/保存/破棄を適用 | Shell登録テスト、既存日英・外観ブラウザー |
| 画面離脱 | Data Routerの単一Blockerでリンク・検索・履歴を保護。保存成功後の遷移は明示許可。beforeunloadで再読込/終了を保護 | unsaved-navigationとsettings-contractのブラウザーBack/検索キャンセル、workspaces成功遷移 |

認可・Session/CSRF・公開URL・Backend API/DB/Transaction/Leaseは変更していない。共有UIから機能Domainへ依存しない。Staffには管理MetadataやResourcesを要求しない。401は従来のログイン経路を維持し、ページを離れたDraftの永続保存は行わない。各Domainの入力・状態遷移の保存判断は専用APIに残す。

U4のルール一括ON/OFFは全件原子的なAPIを新設する別段階であり、U3の既存逐次削除の部分成功表示と混同しない。

## 検証記録

入口は `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build <task>`。ログはリポジトリ内のローカルartifact。ソース・テストを修正した範囲は再検証する。

| タスク | 結果・artifact |
| --- | --- |
| check | exit 0、`artifacts/check/20260925T100632-29c30d2a` |
| test-web 中間 | 157件成功、`artifacts/test-web/20260925T102455-9df323e1` |
| build-web 中間 | 型検査・build成功、`artifacts/build-web/20260925T102557-1e72cc15` |
| test-a11y 中間 | 108件成功、`artifacts/test-a11y/20260925T101313-77592634`。ルーター変更前 |
| test-a11y U3/workspaces | 16件成功、`artifacts/test-a11y/20260925T102201-107e8c03`。日英、320/375/768px、Desktop、追加414px |
| test-web 最終 | 160件成功、`artifacts/test-web/20260925T104129-1df6630d`。未編集Dialog、登録Resource参照、401も含む |
| build-web 最終 | 型検査・build成功、`artifacts/build-web/20260925T104259-ab4b7c49` |
| build-web フォーム更新後 | 型検査・build成功、`artifacts/build-web/20260925T103158-b0bd09a9` |
| check-docs | exit 0、`artifacts/check-docs/20260925T103350-ddc2e348` |
| check-docs 完了記録更新後 | exit 0、`artifacts/check-docs/20260925T104845-5459a017` |
| build-docs | 日英build・公開境界成功、`artifacts/build-docs/20260925T103658-9b19db29` |
| test-a11y 全群 | 116件中108件成功、個人設定8件が変更なしの保存待ちで失敗。`artifacts/test-a11y/20260925T102752-e522d62d`。下記のテスト契約を修正して再検証する |
| test-a11y 修正後 | `dashboard.spec.ts workspaces.spec.ts features.spec.ts` の96件成功、`artifacts/test-a11y/20260925T103538-e068f533`。個人設定8件、Panel/RRのフォーム送信、登録Resource参照を再検証 |
| test-a11y 最終影響範囲 | `workspaces.spec.ts features.spec.ts` の40件成功、`artifacts/test-a11y/20260925T104140-efaaf41f`。最終SaveBarの未編集/編集中表示とDialog保存を再検証 |

全116ブラウザーケースは上記の実行を合わせて受入済み。一つの全群実行が無失敗だったという意味ではない。実装の最終変更で影響を受けるケースを再実行した。

初回の不足import、追加テストのResizeObserver/翻訳設定、jsdomとNode RequestのAbortSignal差を修正した。登録拡張テストのcold lazy importが負荷時に既定1秒を超えたため、入力の出現待ちを5秒にした。機能の受入条件は維持する。個人設定の外観テストは変更なしなら保存無効・破棄で閉じることを検証し、全外観/テーマの確認を維持する。

目視: U3/workspaces artifactの `settings-414-ja.png` と `settings-conditions-en.png`（320px）で、設定ONと条件表示、参照不能ID、未保存/保存バー、Provider未設定と無効ボタンを確認。自動検査は横溢れ、深刻なAxe違反、日英の入力保持・離脱キャンセル・保存再読込を確認する。実Discord/Provider接続・Remote CI・別Linux Host・Stageの成功証拠ではない。

## 文書

日英の `docs/dashboard/saving.md`、architecture、design、CODE_MAP、extending、WEB作業指示に編集と状態表示の契約を反映した。goal/ROADMAP/EXECUTION_PLAN/HANDOFFをU3完了・次はU4へ更新した。一時計画goal.mdはU6まで保持する。
