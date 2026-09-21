# Bot・Domain・DBを変更するとき

先に[設計原則](../ENGINEERING.md)、[責務](../architecture.md)、機能追加なら[拡張手順](../extending.md)を読む。

1. 対象Domainのモデル・Repository・Serviceと入力元Cog/APIを特定する。別GuildのResource、無効化、権限不足の扱いを先に決める。
2. SQLはRepositoryへ置く。Schema変更は `migrations/postgresql/` に番号付きで追加し、適用済みSQLを書き換えない。コンストラクタでDDLを実行しない。
3. 状態更新と配送予約を同一Transactionにする。Lease所有者・Token・期限・revisionを検査し、結果不明の外部操作を無条件に再送しない。部分失敗と復旧に必要な記録を保持する。
4. テストは専用PostgreSQLとUUID Schemaを使う。実環境app.envやDBを流用しない。空DB・更新・再適用・Rollback、競合・無効化・再起動を変更範囲に応じて検査する。
5. コマンド変更はサブコマンド・別名も `docs/reference/commands.json` と日英説明に反映する。用途・引数・権限・応答の公開範囲・例を確認する。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build test-python
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build commands-check
```

APIも変わる場合は[Web作業指示](WEB.md)を併用する。必要な生成タスクは[TOOLS](../TOOLS.md)を参照する。
