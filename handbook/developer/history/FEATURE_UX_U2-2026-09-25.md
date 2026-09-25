# U2 配置と大機能

実施日: 2026-09-25。対象はCommit `fd43651b7b0998808e0e9c909d9479e3b00f5e21`（U0/U1）に対する未コミット作業ツリー。専用計画のU2を実施し、現行仕様は[拡張手順](../extending.md)・[視覚仕様](../design.md)・[構成](../CODE_MAP.md)へ反映した。

## 変更と受入対象

- 24公開機能をサーバー運営2、コミュニティ5、エンゲージメント3、モデレーション9、通知・ソーシャル5へ配置。共通入口は概要とサーバー情報。Backendの機能ID・カテゴリー・parent・保存先は維持した。
- Ticketは概要・受付一覧・受付設定・履歴・統計・設定。受付設定のPanel、配置メッセージ、Form、Team、Tagはグループ内Navigationへまとめた。静的ページと権限はRegistry、受付詳細・Panel編集は機能内Routerが所有する。Staffは概要・受付一覧・履歴のみ利用する。
- RRはメッセージ一覧・Link Group・操作履歴・設定・作成。Link Groupと履歴を専用ファイルへ分離し、設定Dialogの保存先を維持した。
- `modules/tickets` は `tickets/settings`、`modules/reaction_roles` は `reaction-roles` へ接続。既存の詳細・編集・Transcript・Hub経路を保持。Route階層の変更で戻り先がずれるTicket ArchiveとPanel Editorのリンクを絶対経路にした。
- サーバー情報はGuild名・ID、Discord Resourceの件数、Metadataの不足権限を表示する。機能リンク集とTicket概要の重複一覧を撤去し、未使用の `guilds/Settings.tsx` と `tickets/catalog.ts` を削除した。参照・動的登録・文書を検索し、履歴以外の参照がないことを確認。
- 検索・パンくず・Mobileナビは同じ登録を使用。検索はカテゴリー名でも絞り込める。Drawerは縦配置・44pxの操作対象とし、選択後に閉じて遷移先の見出しへFocusを移す。

## 検証

Windows Docker Desktop上のLinuxコンテナ。Host Python/Nodeは不使用。入口は `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build <task>`。ログはローカル `artifacts/` 配下。

| 検査 | 結果・ログ |
| --- | --- |
| check | exit 0、`check/20260925T090356-9c820a08` |
| typecheck | exit 0、`typecheck/20260925T093417-c1fa6d87` |
| test-web | 143件成功、`test-web/20260925T093207-149f28ee` |
| build-web | 幅修正後exit 0、`build-web/20260925T094104-c11c380a` |
| test-a11y | `test-a11y/20260925T093210-fe510651` は100件成功・表示名の期待値8件失敗。該当8件は修正後 `test-a11y/20260925T094104-f4ec31e4` で全件成功。合計108ケースの失敗を解消 |
| 保存と戻りの追加確認 | 全幅・日英8件成功、`test-a11y/20260925T093446-ff3866e1` |
| 幅修正後の配置・導線・撮影 | 全12件成功、`test-a11y/20260925T093859-46ab4048` |
| 受付設定の読込完了後の撮影 | Desktop/320pxの日英4件成功、`test-a11y/20260925T094246-878e29cf` |
| check-docs | 計画・履歴更新後exit 0、`check-docs/20260925T094535-f01e4df9` |

登録拡張、依存境界、全画面経路、内部ページのグループ整合性とnested経路、Staffの管理画面loader拒否をUIテストで検証した。ブラウザーは実SPAと固定HTTP応答を使い、日英・320/375/768px/Desktop、棚卸し画像は414pxも対象にする。保存確認は専用APIへのPayload、再取得と画面への反映を確認するもので、実DB・Discordの受入ではない。

途中の失敗は、表示カテゴリー追加によるテストの同名要素指定、Testing LibraryへPlaywright用の `exact` を渡した型不一致、遅延遷移前の見出しへFocusする問題。修正中にDrawerをcaptureで閉じると通常のページ再読込になることをtraceで特定し、Routerのクリック処理後に閉じる順序へ修正した。先の見出しを除外し、遅延画面の描画を待つ検証は320pxの日英で成功した（`test-a11y/20260925T093050-3c12d2c9`）。

## 画面の確認と範囲

U0の画面案に対し、Desktopでサーバー運営の2機能と共通入口が分かれ、RRに一覧・Link Group・履歴・設定・作成が並ぶことを画像で確認した。320pxのDrawerは上位リンクも縦一列で、カテゴリー内リンクと同じ操作対象を持つ。画像確認で発見した320pxのサーバー選択欄と検索ボタンの重なりは、上部操作を2行にして解消した。選択欄の44px操作対象と重なり不在をブラウザーで検査している。Fixtureの汎用機能名はIDで固定しており、画像内のIDは実APIの翻訳品質の証拠ではない。

Backend/API契約・DB Schemaは変更していない。包括的な設定状態・保存/失敗契約は計画上のU3、ルール再利用はU4/U5、全群CIと一時計画の終了はU6で扱う。独立Linux Host、Remote CI、実Stage、実OAuth/Discord操作は今回のローカル受入に含めない。

U2の受入対象は完了。次はU3で、U2からの残作業はない。ブラウザー108件は単一の成功Runではなく、100件の成功と期待値修正後の8件再実行による確認である。追加の幅修正は12件で、保存と戻りは8件で検証した。最終撮影ではTicket受付設定の主ナビと5つの設定ページ、Desktop/320pxで読み込み後の内容・操作対象を目視した。

最終差分の空白検査と未追跡ファイルの末尾・空白確認は指摘なし。検証用基盤は `docker compose --env-file deploy/compose.env -f compose.tools.yaml down --remove-orphans` で停止し、exit 0を確認した。Commit・Stageは行っていない。
