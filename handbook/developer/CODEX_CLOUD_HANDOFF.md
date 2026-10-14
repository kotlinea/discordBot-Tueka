# Codex Cloud開発の引き継ぎ

更新: 2026-10-14。目的は開発と検証。通常運営や本番配布は行わない。

## 対象

GitHub: `kotlinea/discordBot-Tueka`。準備開始時のローカルmainは`6f13711`。最新リモートの確認とクラウド環境での検証は別途必要。

入口は[AGENTS.md](../../AGENTS.md)と[HANDOFF](HANDOFF.md)。Dashboardの次の作業は[再設計計画](DASHBOARD_REDESIGN_PLAN.md)のR0。見た目の再構成を目的とし、既存のAPI、権限、保存、競合、離脱保護、日英、3外観×light/darkの契約を継承する。

参考画像はこのローカルチャットの添付でありGitHubには含まれない。主参考はMEE6の暗色画面、名前付き左ナビ、設定ごとの横長パネル。Avocloudのカテゴリー別機能タイル、Carl.ggの設定群、Ticketのフィルターと行操作を補助参考とする。具体的な適用案は再設計計画に記載済み。画像自体が必要な比較ではクラウドチャットへ添付する。

## 環境セットアップの指示

リポジトリを読み、必要なツールとサービスを準備する。まずDocker CLI、Linux daemon、Compose plugin、ソースmount、artifactへの書込を確認する。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build check
```

[TOOLS](TOOLS.md)の固定ImageとLockを使う。既存の共通検証が実行できる場合は次を実行する。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build typecheck
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build test-web
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build build-web
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build check-docs
```

Docker daemonを使えない場合は、その制約と実行不能なタスクを記録する。クラウド用の検証方法を同じLockと設定から検討し、実装・結果を明記する。Host上で別の依存を入れて標準受入が通ったことにはしない。ブラウザー/E2E実行の可否も確認する。

環境セットアップの成功は検証コマンド、終了結果、ログで判定する。Docker CLIの存在だけで準備完了としない。

## 開発サーバー

共通タスクが使える環境では次のUI開発サーバーを使用する。

```text
docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build --service-ports dev-web
```

これはUI開発用。API接続が必要な画面の確認は別途テスト基盤や開発APIの状態を確認する。実Bot Tokenや運営DBをコピーして画面確認の前提にしない。

## HTTPSの扱い

クラウド側のプレビューURLと公開証明書を持つStageは区別する。環境が提供するプレビューの公開範囲、HTTPS URL、OAuth callbackへの使用可否を確認してから採用する。提供されていないURLを作ったことにしない。Host Caddyや独自ドメインの設定だけを作成して、公開HTTPSの確認成功とはしない。

## 最初の開発作業

1. 環境のセットアップ結果と未対応の検証を記録する。
2. R0のShell、概要、Welcome、Ticket Inboxを試作し、Desktopと375px、日本語と英語で比較できる成果物を用意する。
3. 日付付きhistoryへ差分、実行コマンド、結果、未検証事項と次の段階を記録する。

ローカルユーザー個人のskillsはクラウドに自動同期されない。必要なskillがない場合は、実装開始前に利用可否を確認する。再設計計画には視覚方針と既存契約を記載している。

## 同期範囲

ソースと文書をGit経由で同期する。実app.env、Token、暗号鍵、運営DB、Transcript、Backup、ログ、node_modules、venv、生成distは同期しない。検証用DBは検証基盤内で作成し、既存環境のVolumeを再利用しない。

## 準備時点の結果

2026-10-14、専用ブランチ`codex/cloud-development-setup`へ本書と再設計計画を準備。文書検査とステージ済み差分の空白検査は成功した。

- 文書検査: `docker compose --env-file deploy/compose.env -f compose.tools.yaml run --rm --build check-docs`、終了0。
- ログ: `artifacts/check-docs/20261014T052457-eb14452f`。
- Codex Cloud: ブラウザーでログインを確認したが、環境一覧と環境作成のGitHub接続の読み込みが失敗。再試行後もセットアップ開始ボタンは無効。
- クラウド環境の作成・公開、依存導入、クラウドでの開発と検証は未実施。これらを準備完了とは扱わない。

接続が回復した後、リポジトリと専用ブランチを選び、本書の指示でセットアップを開始する。GitHub同期の成功は別途pushとリモートのCommit確認で記録する。

## 接続回復後の結果

GitHub接続が回復し、Codex Cloudの環境セットアップを開始した。Git CLIのpushは認証不足で失敗したため、GitHub連携を使って専用ブランチへ2文書を追加し、読み取りで確認した。リモートの文書追加Commitは`6ff3468a81fbd911a2d86110cc5af10c4b09fe84`、ローカルの文書Commitは`e2ffb5d`。同じ文書を別のCommitで保存しており、ブランチの履歴が完全同期したとは扱わない。

セットアップチャット: `01a138e0-c259-7562-826c-98679808a09a`。クラウド側で引き継ぎ資料とR0計画を確認した。

- クラウド側確認済み: Docker／Compose、GitHub読み取り、Compose設定、テスト用PostgreSQLの起動とSQL実行。
- 未完了: Compose check、UI検証・ビルド、開発サーバー起動、プレビューURL、HTTPS、OAuth callback。
- インストールスクリプトと起動用スキルをドラフトへ設定。利用できるユーザーは「自分のみ」、秘密情報と環境変数は未追加。
- 固定DebianアーカイブとPlaywright Imageの取得に必要な`snapshot.debian.org`、`centralus.data.mcr.microsoft.com`のネットワーク許可を追加するドラフトを確認した。
- 「下書きを保存」は自動承認審査で拒否された。永続的なネットワーク許可の対象と範囲を明示したユーザー承認が必要という理由。別経路で保存や公開を行わない。

次は2ドメインの許可と設定保存についてユーザー承認を得てから保存し、クラウド側で未完了の検証を再実行する。成功を確認した範囲で環境を公開し、R0試作へ進む。

