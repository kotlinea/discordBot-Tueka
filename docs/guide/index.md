# Tuekaについて

Tuekaは、Discord Bot、管理ダッシュボード、ソーシャル通知Workerで構成されます。サーバーごとの設定は共通PostgreSQL DBへ保存され、BotとWorkerが同じ状態を参照します。

## 主な機能

| 分類 | 機能 |
| --- | --- |
| Moderation | AutoMod、Anti-Spam、Anti-Raid、Warnings、手動処置、ログ |
| Community | 入退室、初期Role、レベリング、Ticket、Reaction Roles、一時VC、ライブ統計 |
| Engagement | 投票、ミニゲーム |
| Social | YouTube、Twitch、X、TikTok、Instagram通知 |

設定を変更できるのはDiscord OAuthで対象サーバーの管理権限を確認できたユーザーです。Ticket Staffは、許可されたTicket画面だけを利用できます。

## データの所在

設定、ケース、イベント、配送状態は`DATABASE_URL`のPostgreSQLへ保存されます。Ticket Transcriptは暗号化してローカルまたはS3互換ストレージへ保存できます。秘密値は`.env`だけで管理します。
