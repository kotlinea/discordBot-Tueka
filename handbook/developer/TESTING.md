# テストと検証

実行方法の正本は[共通Composeタスク](TOOLS.md)です。Host Python／Node／npmや専用venvは不要です。実行環境はDockerfile.toolsの用途別ターゲットで構築します。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build ci
```

CIも同じ入口をpython／web／runtime／secretsの4群に分けて実行します。専用PostgreSQLのreadiness、生成物の差分、日英Docs・公開境界、モバイル／Accessibility、Compose・Recovery・Caddyの受入を含みます。通常のアプリ資格情報はテストへ渡しません。

変更箇所に応じた単独タスクと終了後の片付けはTOOLS.mdを参照してください。ログとブラウザtraceはartifacts配下へ保存します。生成物の更新には明示的なgenerateタスクを使います。

Windows／Linuxのクリーンcheckoutでcheck、生成、build、setup受入を実行し、Hostの開発ツールを使わないことを確認します。Linux所有権、空白・日本語パス、ポート競合、Migration失敗、再実行、鍵・Volume保持も受入対象です。Remote CIと実Stageの証拠は[実行計画](EXECUTION_PLAN.md)へ別々に記録します。

過去のbaseline・ネイティブ環境での結果は[進捗履歴](history/PROGRESS0910.md)を参照してください。
