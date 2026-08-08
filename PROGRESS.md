# DiscordBot-Tueka 現状・進捗

最終更新: 2026-08-08

## ダッシュボード（実装済み）

- Discord OAuth2ログイン（`identify guilds`）、署名付きCookie、サーバー側の期限付きセッション、OAuth state検証を追加。
- Bot導入済みかつAdministrator権限のあるサーバーだけを一覧・編集対象に限定。
- 管理ログ／歓迎チャンネル、初期ロールをWebから安全に更新可能。
- 設定・XP・警告数をSQLiteへ統合し、`migrate_json.py` による従来JSONの一回限りの移行を追加。
- `deploy/` にsystemdとNginxのVPS運用テンプレートを追加。

## 今回整備した基礎

- 単一の `bot.py` を起動専用にし、機能を Cog に分離した。
- トークン、Gemini APIキー、チャンネル/ロールIDを `.env` から読む構成に変更した。
- `.env.example`、依存関係一覧、`.gitignore`、ギルド単位のJSONストレージ層を追加した。
- 管理系コマンドにDiscord権限チェックを追加した。

## 現在の機能

| 区分 | 内容 | 実装 |
| --- | --- | --- |
| 基本 | help, ping, echo, 安全な四則演算, roll, userinfo, serverinfo, shutdown | `cogs/general.py` |
| AI | `/gemini` によるGeminiへの質問（APIキー設定時） | `cogs/ai.py` |
| レベル | 60秒ごとのXP加算、`/rank`、`/leaderboard`、レベルアップ通知 | `cogs/leveling.py` |
| モデレーション | 禁止語CSVの検知・削除・警告、管理ログ設定、確認付き削除 | `cogs/moderation.py` |
| 監査ログ | メッセージ送信・編集・削除の管理チャネル通知 | `cogs/audit_log.py` |
| 入退室 | 歓迎/退出メッセージ、初期ロール付与 | `cogs/welcome.py` |

## 実行方法

1. ` .env.example` を `.env` にコピーし、**新しく発行した** `DISCORD_TOKEN` を設定する。
2. 必要ならGeminiキーとDiscordのチャンネル/ロールIDを設定する。
3. `pip install -r requirements.txt`
4. `python bot.py`

## 要対応・注意点

- 旧 `bot.py` にDiscordトークンとGemini APIキーが平文で存在した。今回ソースから削除したが、露出済みの値は直ちに無効化・再発行すること。
- 旧実装のランクカード画像と、サーバー/チャネル/プロフィール/ロール変更の詳細ログは、今回の基礎整理では移植していない。仕様確認後に専用Cogとして追加する。
- `data/` は実行時データなのでGit管理外。既存データ形式とは互換性がないため、必要なら移行スクリプトを用意する。
