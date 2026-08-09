# DiscordBot-Tueka 現状・進捗

最終更新: 2026-08-09

実VPSでのみ実施できる確認は [DEPLOYMENT_TODO.md](DEPLOYMENT_TODO.md) に分離している。

## ダッシュボード（実装済み）

- Discord OAuth2ログイン（`identify guilds`）、署名付きCookie、サーバー側の期限付きセッション、SQLiteでの短時間・一回限りOAuth state検証を追加。
- Bot導入済みかつAdministrator権限のあるサーバーだけを一覧・編集対象に限定。
- 管理ログ／歓迎チャンネル、初期ロールをWebから安全に更新可能。
- 設定・XP・警告数をSQLiteへ統合し、`migrate_json.py` による従来JSONの一回限りの移行を追加。
- `deploy/` にsystemdとNginxのVPS運用テンプレートを追加。
- カテゴリ別の機能カード、機能ごとの有効／無効化、詳細設定、日英・テーマ切替を追加。
- 新規モジュールはすべて無効で開始し、必須設定が不足した状態での有効化は保存を拒否する。
- 機能追加時の設計・実装・検証手順を `docs/FEATURE_MODULE_GUIDE.md` に記録。

## 安全な管理基盤（実装済み）

- モデレーションを警告、タイムアウト、キック、追放へ拡張。処置履歴には理由、実行者、期限、DM送信結果をSQLiteに保存し、管理ログ有効時は記録する。
- 警告による自動エスカレーションは既定で無効。ダッシュボードで回数、処置、タイムアウト時間、DM通知を明示設定した場合だけ実行する。
- `chat_filter` はキーワード、長さ・危険パターンを制限した正規表現、Google Safe BrowsingのURL検査を提供する。Safe Browsingの結果はURLハッシュ単位で期限付きキャッシュし、API障害時はメッセージを削除しない。
- `anti_spam` は時間窓内の投稿数、メンション数、重複数を検知し、削除または設定済みのタイムアウトを行う。
- `reaction_roles` はダッシュボードで投稿先と最大25件の安全なロールを選択し、保存時にボタンパネルをDiscordへ投稿できる。管理権限、Bot管理ロール、`@everyone`、Botより上位のロールは対象外。
- すべての新モジュールはギルドごとに初期無効で、無効時はイベント処理・コマンドを停止する。

## コミュニティ自動化（実装済み）

- `live_stats` は設定したボイスチャンネル名をメンバー数・Bot数・ロール数から更新する。
- `temporary_voice` はトリガーVCへの参加で個人用VCを作成し、空になったものだけをSQLiteの追跡情報に基づいて削除する。
- `tickets` はスタッフロールと作成者だけが閲覧できるテキストチャンネルを作成する。クローズ時には最大200件の議事録をSQLiteへ保存し、任意のログチャンネルへ通知する。

## 参加促進・信頼度（実装済み）

- `advanced_polls` は最大10択、任意の終了時間・画像URL、ボタンによる投票変更、SQLiteの原子的な票数更新を提供する。
- `minigames` はモジュールが有効なサーバーだけで実行できるじゃんけんコマンドを提供する。
- `trust_score` は違反イベントから0〜100のスコアと理由を管理者だけに表示する。自動ミュート・キック・追放は行わず、管理者が信頼イベントを手動解除できる。保持期間もギルドごとに設定可能。

## 今回整備した基礎

- 単一の `bot.py` を起動専用にし、機能を Cog に分離した。
- トークン、Gemini APIキー、チャンネル/ロールIDを `.env` から読む構成に変更した。
- `.env.example`、依存関係一覧、`.gitignore`、ギルド単位のJSONストレージ層を追加した。
- 管理系コマンドにDiscord権限チェックを追加した。

## 現在の機能

| 区分 | 内容 | 実装 |
| --- | --- | --- |
| 基本 | help, ping, echo, 安全な四則演算, roll, userinfo, serverinfo | `cogs/general.py` |
| AI | `/gemini` によるGeminiへの質問（APIキー設定時） | `cogs/ai.py` |
| レベル | テキスト／VC別XP、通知チャンネル、累積ロール報酬、`/rank`・`/leaderboard`・`/vcrank`・`/vcleaderboard` | `cogs/leveling.py` |
| モデレーション | 禁止語CSVの検知・削除・警告、管理ログ設定、確認付き削除 | `cogs/moderation.py` |
| 監査ログ | メッセージ送信・編集・削除の管理チャネル通知 | `cogs/audit_log.py` |
| 入退室 | 歓迎/退出メッセージ、初期ロール付与 | `cogs/welcome.py` |
| 安全機能 | 警告・制裁、チャットフィルター、スパム対策、リアクションロール | `cogs/safety.py` |

## 実行方法

1. ` .env.example` を `.env` にコピーし、**新しく発行した** `DISCORD_TOKEN` を設定する。
2. 必要ならGeminiキーとDiscordのチャンネル/ロールIDを設定する。
3. `pip install -r requirements.txt`
4. `python bot.py`
