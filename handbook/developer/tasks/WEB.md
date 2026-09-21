# API・Dashboardを変更するとき

先に[API契約](../api.md)、[視覚仕様](../design.md)、[設計原則](../ENGINEERING.md)を読む。

- Routerは入力・認可・応答、Serviceは状態遷移を担当する。Session、CSRF、Guild所属、管理者/Staff権限、revision競合を検証する。
- HTTPのSwagger/OpenAPIはDevかつ `TUEKA_API_DOCS_ENABLED=true` の場合だけ有効。Stage/Prodと通常設定は404を維持する。型生成はオフラインで行う。
- 画面経路、Feature Registry、機能別Docsリンク、日英翻訳を揃える。Tokenと既存コンポーネントを使い、機能変更と見た目の再設計を混ぜない。
- 保存・再読込、失敗時の入力保持、409、無効化、空状態、キーボード、モバイルを確認する。一般メンバーとGuild管理者の操作権限を明確にする。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build api-generate
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build api-check
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build typecheck
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build test-web
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build test-a11y
```

生成は契約を変更した場合に行い、差分をレビューする。Backend変更の検証は[BACKEND](BACKEND.md)、Docsの変更は[文書基準](../DOCUMENTATION.md)に従う。
