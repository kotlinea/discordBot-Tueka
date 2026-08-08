# DiscordBot-Tueka 現状・進捗

最終更新: 2026-08-08

## ダッシュボード（実装済み）

- Discord OAuth2ログイン（`identify guilds`）、署名付きCookie、サーバー側の期限付きセッション、SQLiteでの短時間・一回限りOAuth state検証を追加。
- Bot導入済みかつAdministrator権限のあるサーバーだけを一覧・編集対象に限定。
- 管理ログ／歓迎チャンネル、初期ロールをWebから安全に更新可能。
- 設定・XP・警告数をSQLiteへ統合し、`migrate_json.py` による従来JSONの一回限りの移行を追加。
- `deploy/` にsystemdとNginxのVPS運用テンプレートを追加。
- カテゴリ別の機能カード、機能ごとの有効／無効化、詳細設定、日英・テーマ切替を追加。
- 新規モジュールはすべて無効で開始し、必須設定が不足した状態での有効化は保存を拒否する。
- 機能追加時の設計・実装・検証手順を `docs/FEATURE_MODULE_GUIDE.md` に記録。

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

