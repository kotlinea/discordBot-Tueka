# 機能中心の構成計画の制定

記録日: 2026-09-21。対象Commit: `2b7050cb26acc85ea6edba080d5bf2af55458a18` と今回の文書追加。開始時の作業ツリーは変更なし。

ユーザーの依頼に基づき、ルートの `goal.md` に今回専用の一時計画を制定した。ENGINEERINGの「横方向の疎結合」に沿って、Bot/API・Dashboardのカテゴリー/機能別配置、Registry、既定実装からのoverride、共有Button/EmbedEditor、段階的移行と受入条件を整理した。

実装は未着手。アプリコード、既存DB、配布設定、全体計画の受入状態は変更していない。確定仕様は実装時に現行handbookへ移し、完了時に一時計画を削除する。

## 検証

Windows Host / Docker DesktopのLinuxコンテナでリポジトリルートから実行した。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build check
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build check-docs
git diff --check
```

- `check`: exit 0。`artifacts/check/20260921T052052-0939a2e5`。
- `check-docs`: exit 0。`artifacts/check-docs/20260921T052338-00d6e3b4`（goal.md制定後）。
- `git diff --check`: exit 0。新規未追跡ファイルはこのコマンドの対象外のため、別途空白とリンクを確認する。
- 通常権限でDockerへのアクセスが拒否されたが、権限付き実行で解消。ログはローカルartifactsにあり、Remote CIの証拠ではない。

機能回帰、Linux Host、Remote CI、実Stageは未検証。計画制定の阻害要因なし。次の作業はG0の全入口対応表と変更前baselineの確立。
