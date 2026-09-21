# Docker・設定・配布・復旧を変更するとき

先に[共通タスク](../TOOLS.md)、[運用者ガイド](../../operator/README.md)、[実行計画](../EXECUTION_PLAN.md)を読む。

- Host前提はGitとLinuxコンテナ対応Docker/Compose。Python、Node、npm、Playwright、PostgreSQL、専用venvをHostへ要求しない。OSラッパーはDockerの確認に限定する。
- Imageはdigest、Pythonはhash付きLock、npmはpackage-lockで固定する。CIとローカルは同じComposeタスクを使う。開発ツールや内部資料を本番Imageへ追加しない。
- Dev/Stage/Prodのアプリ設定の正本は環境別 `app.env`。configureは全対応項目を生成し、再実行時は不足項目だけ補完する。秘密値・鍵・既存設定を保持する。
- `setup check → configure → build → start` を維持する。ドラフト設定と起動可能なdeployment設定を区別し、設定不足では先に進めない。本番は受入済みStageと同じImageを使用する。
- エラーには対象ファイル・項目・不一致・修正方法・再開段階を示す。秘密値を引数・ログ・設定全文artifactへ出さない。
- socketは管理タスクだけへ渡す。daemon側bind/secretパスを共通変換し、空白・日本語・Windowsパスを扱う。remote contextは拒否する。所有権をリポジトリ全体へ再帰変更しない。
- テスト資源は実行単位で分離し、その実行が作成した資源だけ片付ける。通常タスクへDB初期化・運用Volume削除を追加しない。
- Recoveryの書き込み停止、復旧保留、明示解放を維持する。CaddyはHostで稼働し、loopback転送と内部経路404を維持する。実Host導入・DNS・公開証明書・systemd操作は運用者の実機手順で行う。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build ci --group runtime
```

設定・DB層の変更には `ci --group python`、依存やImage変更には関連するweb/secrets群も選ぶ。受入結果はWindowsローカル、Linuxローカル、Remote CI、実Stageに分けて記録する。
