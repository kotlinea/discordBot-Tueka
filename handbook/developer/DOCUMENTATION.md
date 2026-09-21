# ドキュメントの編集基準

ドキュメントはリポジトリのコードと設定を基準に更新します。読者が前のVersionを知っていることを前提にしません。

## 読み手と配置

| 配置 | 読み手 | 書く内容 |
| --- | --- | --- |
| docs/ | 一般メンバー、サーバー管理者、モデレーター | 目的、操作、引数、権限、結果、上限、問題の解決 |
| handbook/operator/ | システムの導入・配布・保守担当 | 前提、完全なコマンド、設定先、影響、成功確認、障害対応 |
| handbook/developer/ | コード・契約・リリース担当 | 設計、実装境界、検証、計画、変更履歴 |

READMEとdeploy/READMEも利用者・運用者の入口として書きます。公開Docsは日本語・英語を同じ変更で更新します。

## 文体

- 操作する人に向けて、使える機能と結果を現在形で紹介します。
- 「旧ルート」「現在の実装に合わせています」「廃止しています」など、変更前を前提にした説明を利用者・運用者資料へ書きません。
- 「出力しません」「同じServiceへ委譲」などの実装説明ではなく、出力する項目や読者が行う操作を記載します。
- 比較や実装経緯が必要な場合は開発者向け履歴へ記録します。
- 権限不足、利用上限、データ損失、起動保留など、利用者の判断に必要な制約は明記します。肯定形への変更を理由に安全条件を省略しません。
- 実装がない機能を使えるものとして紹介しません。計画と実施結果は実行計画・進捗で管理します。

例: 「ログに本文を出力しません」ではなく「ログには時刻、サービス名、イベント種別、HTTPステータスが表示されます」と記載します。

## 内容の照合

1. 機能説明はFeature Registry、Cog、API、設定モデル、Dashboardの入力と照合します。
2. コマンド一覧はcommands.jsonと実Bot登録を照合します。生成タスクが保持するページ冒頭の説明も日英で確認します。
3. 導入・運用コマンドはComposeタスクとCLIの引数を確認します。対象ディレクトリ、必要な編集、実行順、成功確認を添えます。
4. 環境変数はdeploy/app.env.exampleと設定ローダー、配布条件を確認します。
5. 外部製品の導入手順は公式資料で確認し、該当ページへリンクします。
6. 実行証拠はWindows、Linuxコンテナ、Linux Host、Remote CI、実Stageを分けます。

## 検査

リポジトリルートで実行します。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build check-docs
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build commands-check
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build build-docs
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build test-docs-a11y
```

check-docsはリンク、公開境界、利用者・運用者向けの禁止表現、削除済みタスク入口を検査します。意味や機能の正確さはコードとのレビューで確認します。

過去の記録は `history/` へ保存し、記録時点を明示します。現行ガイドから古い操作手順へ誘導しないようにします。全Markdownの点検対象は[文書点検台帳](history/DOCUMENTATION_AUDIT.md)を参照してください。
