# 開発者向けガイド

コード修正、設計、検証、リリース対象定義の正本です。Dashboard上には公開しません。

- [現在の実行計画](EXECUTION_PLAN.md)
- [進捗・実施証拠](PROGRESS0910.md)
- [設計と責務](architecture.md)・[機能追加](extending.md)・[API契約](api.md)
- [テスト](TESTING.md)・[文書移管台帳](DOCUMENT_MAP.md)
- [運用者との受渡し](../operator/README.md)

公開Docsを変更したら日英を同時更新します。全コマンドの契約と説明は `docs/reference/commands.json` と日英commandsページで管理し、`python scripts/generate_commands.py --check` で実Bot登録と照合します。検査は専用PostgreSQLで行い、Discordへ接続・同期しません。契約変更はまず `python scripts/generate_commands.py` の出力を確認し、説明・例・権限もレビューします。

Swagger/OpenAPIは `TUEKA_ENV=dev` と `TUEKA_API_DOCS_ENABLED=true` を両方設定した開発環境だけで利用します。型生成は `python scripts/generate_api.py --check` を使用し、HTTP資料公開には依存しません。

Docker環境のアプリ設定は環境別app.envだけを使用します。ルート.envの暗黙読込みはありません。Host上のオフラインテスト・型生成は専用のProcess環境変数を渡します。これはDev／Stage／Prodの設定元ではなく、実環境のapp.envや実DBをテストへ流用しません。
