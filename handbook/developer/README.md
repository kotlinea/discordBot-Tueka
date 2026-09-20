# 開発者向けガイド

コード修正、設計、検証、リリース対象定義の正本です。Dashboard上には公開しません。

- [現在の実行計画](EXECUTION_PLAN.md)
- [ドキュメントの編集基準](DOCUMENTATION.md)・[点検台帳](DOCUMENTATION_AUDIT.md)
- [進捗・実施証拠](PROGRESS0910.md)
- [設計と責務](architecture.md)・[機能追加](extending.md)・[API契約](api.md)
- [テスト](TESTING.md)・[文書移管台帳](DOCUMENT_MAP.md)
- [運用者との受渡し](../operator/README.md)

公開Docsを変更したら日英を同時更新します。全コマンドの契約と説明は `docs/reference/commands.json` と日英commandsページで管理し、`docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build commands-check` で実Bot登録と照合します。検査は専用PostgreSQLで行い、Discordへ接続・同期しません。契約変更はまず `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build commands-generate` の出力を確認し、説明・例・権限もレビューします。

Swagger/OpenAPIは `TUEKA_ENV=dev` と `TUEKA_API_DOCS_ENABLED=true` を両方設定した開発環境だけで利用します。型生成は `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build api-generate` を使用し、HTTP資料公開には依存しません。

Docker環境のアプリ設定は環境別app.envだけを使用します。ルート.envの暗黙読込みはありません。共通タスクのオフラインテスト・型生成には専用DBの接続設定を渡します。これはDev／Stage／Prodの設定元ではなく、実環境のapp.envや実DBをテストへ流用しません。

開発・検査・依存更新・運用の実行入口は[共通Composeタスク](TOOLS.md)です。
