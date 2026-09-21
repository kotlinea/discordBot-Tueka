# G2 welcome試験移行・共有UI

2026-09-21。G1を含む作業ツリーで実施。Windows Host / Docker DesktopのLinuxコンテナ。既存変更を保持した。

## 変更と受入

- welcomeをカテゴリー配下のCog・設定モデル・API設定Factory・UI画面へ接続。APIと共通項目描画からwelcome専用分岐を除去した。
- autoroleを独立Cogへ分離し、Bot拡張は17個。公開24機能・103コマンド・URL・保存形式を維持。コマンド生成物の変更はwelcomeの実装モジュール名だけ。
- 共通設定画面に項目描画/見出し/追加操作の差し替えを設け、Buttonと既存EmbedEditorを共有フォルダーへ整理。Embed制約・Ticket変数・保存は呼出元が所有する。
- 保存→再読込→Bot送信、無効化、認可/CSRF/revision、403/409/422時の入力保持、再取得とGuild切替時の編集状態、日英・keyboard・320/375/414/768/1440pxを確認。画面画像も目視した。

## 検証

入口: `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build <task>`。
ログ: `artifacts/<task>/<実行ID>/`。下表はexit 0。

| task | 実行ID・結果 |
| --- | --- |
| check | `20260921T061634-6cffe240` |
| test-python | `20260921T062835-571c0ea6`、393件 |
| test-web | `20260921T063154-3fdf6b07`、32件 |
| typecheck | `20260921T062251-96ee6998`。最終型検査はbuild-webにも含む |
| api-check | `20260921T062429-2bc0f578`、公開差分なし |
| commands-check | `20260921T063021-64851143`、103件一致 |
| build-web | `20260921T063255-7a54856b`、最終型検査を含む |
| test-a11y | `20260921T063309-78db5e32`、56件 |
| check-docs | `20260921T063620-5a2e30d6` |

G2完了、残作業なし。`git diff --check`と追加ファイルの末尾空白検査も成功。初回のテスト参照・ブラウザーAPI mock不足を修正済み。
実Discord/OAuth、Linux Host、Remote CIは未検証。次はG3。他のBackend機能をカテゴリー順に移行し、`cogs/community/__init__.py` 内の統計/一時VCも機能別入口へ分ける。
