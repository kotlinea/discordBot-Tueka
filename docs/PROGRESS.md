# DiscordBot-Tueka 現状・進捗

最終更新: 2026-08-14

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

- ダッシュボードを「Moderation」ハブと AutoMod / Anti-Spam / Anti-Raid / Warnings・Infractions / Moderation Actions / Moderation Logs の6画面へ再編した。用途別フォームと共通の高度設定、ルール複製、副作用なしプレビューを提供する。
- `moderation_rules` と `moderation_events` を中心に、message create/edit、reaction add、member join/remove を同じ Event → Trigger → Conditions / Exemptions → Actions → Case / Log パイプラインで処理する。
- リアクション連打、類似投稿、Unicode・カスタム絵文字・スタンプ、Join/Leaveレート、新規アカウント比率、フィッシングリンクを検知できる。Bot/Webhookは既定除外で、IDまたは対象チャンネルを明示したルールだけが評価する。
- `/mod` に Warn、Timeout/解除、Kick、Ban/Unban、Softban、Purge、Lock/Unlock、期限付きLockdown/解除を追加した。従来コマンドは互換エイリアスとして維持し、ダッシュボード処置も同じ永続キューとModeration Serviceへ流す。
- LockdownのoverwriteはSQLiteへスナップショット保存し、期限・手動解除・再起動復旧に対応する。管理者による事後変更と競合したチャンネルは上書き復元せず、結果をイベントへ記録する。
- 旧AutoModルール・イベント・ポイント・ケースをIDリンクを保って汎用テーブルへ冪等移行し、内容系をAutoMod、レート系をAnti-Spamへ分類する。

- ギルド単位の`automod_rules`を追加し、13種類の検知器、AND条件、全体／ルール別例外、監視モード、優先順位、停止フラグ、順序付き複数アクションを提供する。
- キーワード／ワイルドカード／許可語、タイムアウト付き正規表現、Discord招待、正確なドメイン境界、Google Safe Browsing、投稿／重複／メンション／リンク／添付レート、大文字率、メディア限定、ハニーポットを扱う。
- モデレーション処置を共有サービスへ集約し、警告ポイント、タイムアウト、Kick、Ban、一時Ban、DM、通知、削除、ログの結果をAutoModイベント・ケース番号と関連付ける。
- ポイントは失効期間と複数しきい値を持ち、下から上へ横断した最高段階だけを実行する。一時Ban解除はSQLiteスケジュールから再起動後も再開する。
- Safe Browsingは共有HTTPクライアント、同時実行制限、正規化URLのハッシュキャッシュ、障害時fail-openを使用する。レート状態はTTL回収し、ギルド・ユーザー単位ロックとイベント冪等化で重複処置を防ぐ。
- 旧`moderation`禁止語、`chat_filter`、`anti_spam`、警告数は起動時に一度だけトランザクション移行する。旧設定はロールバック用に残すが、メッセージ評価は新AutoMod Cogだけが行う。
- ダッシュボードは全体設定、ルールCRUD／複製、例外、ポイントしきい値、権限・リソース検証、副作用なしプレビューを提供する。本文証跡は最大1000文字で、機密チャンネル除外と保持期限を適用する。
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
| AutoMod / Anti-Spam / Anti-Raid | 共通ルール基盤、内容・レート・リアクション・Join/Leave検知、例外、複数処置、証跡 | `cogs/automod.py`, `automod/` |
| モデレーション | `/mod`、共有処置サービス、警告・ポイント、Timeout、Kick、Ban/Unban、Softban、Lockdown | `cogs/moderation_commands.py`, `automod/service.py` |
| 監査ログ | メッセージ送信・編集・削除の管理チャネル通知 | `cogs/audit_log.py` |
| 入退室 | 歓迎/退出メッセージ、初期ロール付与 | `cogs/welcome.py` |
| 安全機能 | 手動モデレーション、リアクションロール、旧設定の移行互換 | `cogs/safety.py` |

## 実行方法

1. ` .env.example` を `.env` にコピーし、**新しく発行した** `DISCORD_TOKEN` を設定する。
2. 必要ならGeminiキーとDiscordのチャンネル/ロールIDを設定する。
3. `pip install -r requirements.txt`
4. `python bot.py`
