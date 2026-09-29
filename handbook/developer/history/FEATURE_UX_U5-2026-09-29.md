# U5 — ルールの再利用と一括操作

対象: `9e1c6bb58961b1a472f4eff6c1ad87a8d8b6a25d` からの作業ツリー。既存のU4変更とユーザーのstagingを保持。Windows / Docker Desktop Linuxコンテナで検証。

状態: U5ローカル受入完了。U5残作業なし。次はU6の全体受入。

## 実装と受入範囲

AutoMod・Anti-Spam・Anti-Raidの作成入口をFeature Registryに登録した。既定値はBackendのテンプレートAPIから取得し、複製はID・revision・時刻を持たない無効の未保存ドラフトとする。元の条件・例外・処置・Trigger固有値を保持し、画面補助値を保存Payloadから除外する。Trigger入力と一括操作確認を専用コンポーネントへ分離した。

一覧で保存済みルールを選択し、単一の状態変更APIへID/revisionを送る。確認画面は件数・監視/実行モード・必要権限・不足設定・消失Resource・親停止を表示する。409では選択と古いrevisionを保持し、明示再取得後に再確認する。順序/削除の未保存操作と一括状態変更を同時に実行しない。保存中の再送・離脱を共有hookで防ぐ。

日英の作成・テンプレート・複製・一括操作と処置設定文言、利用者ガイドを更新した。設計・構成・拡張手順に各コンポーネントの責務を記載した。

| 条件 | 検証内容 |
| --- | --- |
| 再利用と独立性 | 3 Familyで作成→別Channelへの複製→保存。元のID/内容を保持し、ON→OFF→ONと再読込で件数不変 |
| 入力保持 | 保存422、テンプレート取得失敗、離脱取消、参照先消失でもドラフトを保持。テンプレート置換と破棄は明示操作 |
| 一括更新の失敗 | 403/422/409で全件不変更。選択保持、競合時の再取得・再確認、保存中の二重送信とEscapeを検査 |
| 実行条件 | 親停止、必須設定不足、参照先消失、Bot権限不足を区別。無効化は不完全な設定でも可能 |
| データ変換 | Domain値のdeep copy、編集対象外のconfig/条件/例外保持、画面補助値の除去を単体検査 |
| 操作と表示 | 日英、320/375/768/Desktop、追加414px、keyboard・Focus・Axe・44pxの操作領域を検査 |

## 検証記録

共通入口: `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build <task>`。

| タスク | 結果・artifact |
| --- | --- |
| check | 成功、`artifacts/check/20260929T092307-01221963` |
| test-python | 全428件成功、`artifacts/test-python/20260929T094831-007970bd` |
| test-web | 全163件成功、`artifacts/test-web/20260929T094619-5ac9ff6b` |
| api-check | 成功、`artifacts/api-check/20260929T094831-917b27e5` |
| build-docs | 日英成功、`artifacts/build-docs/20260929T094620-b57af175` |
| build-web | 型検査・本番build成功、`artifacts/build-web/20260929T095622-133e109e` |
| test-a11y rule-operations.spec.ts dashboard.spec.ts --grep 'rule ' | 最終56ケース成功、`artifacts/test-a11y/20260929T095609-c4b0c508` |
| check-docs | 成功、`artifacts/check-docs/20260929T095950-9ac98a8f` |

`git diff --check` と未追跡ソース・文書の末尾空白検査も成功。既存のstagingを変更せず、検証用toolsを停止して終了した。

U0の画面案とDesktop/320pxの一覧・確認Dialog画像を照合した。親停止は機能の状態領域、ルールの有効状態は各行に分かれ、対象Channel・モード・編集/複製を一覧から確認できる。Desktopは表、狭い画面は行内を縦配置し、操作の重なりを解消した。確認Dialogは狭い画面でスクロールして確定操作へ進める。画像は最終ブラウザーartifactの `dashboard/frontend/test-results/rule-operations-rule-lifecycle-automod-ja-*/` に保存した。

途中で型検査のunknown描画、登録に伴うパンくず期待値、選択肢に一致する曖昧なラベルを修正した。ブラウザー検査で見つかったタブレットの順序ボタン重なりと、一覧上部リンクの操作領域不足を修正した。Switchは操作可能な周囲labelを44px検査の対象とする。失敗の記録は `artifacts/test-a11y/20260929T094122-b4cea60b` と `20260929T094725-8fde56af` に保持する。

ブラウザーは実SPAとHTTP fixtureによるローカル検証。Pythonは専用PostgreSQLでAPI/Transactionを検証する。実Discord処置、Provider接続、独立Linux Host、Remote CI、Stageの成功を意味しない。全体受入はU6で扱う。
