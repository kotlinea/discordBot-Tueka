# セキュリティとプライバシー

## 認証と権限

DashboardはDiscord OAuthでログインし、Session Cookieを使います。設定更新時にはCSRFとGuild管理権限、対象Channel・Role・Emojiの所属を確認します。Ticketの操作と閲覧には担当Teamや作成者の権限も適用されます。

Stage／ProdはHTTPSとSecure Cookieを使用します。SESSION_SECRETはconfigureが環境ごとに生成します。

## 資格情報の保管

Discord Token、OAuth Secret、SNS API Key、Webhook Secret、暗号鍵、S3 Credentialは環境別app.envに設定します。設定ディレクトリとBackupはアクセス制限付きで管理してください。暗号化データの復元には、保存時と同じ世代の鍵が必要です。

## 保存データ

| データ | 保存内容・管理方法 |
| --- | --- |
| Moderationの証跡 | 本文は最大1000文字。対象Channelと保持期限を設定 |
| Socialの配送履歴 | イベント情報と配送状態。終了したQueue履歴は30日 |
| Ticket | 回答、本文、Note、Transcriptを暗号化。保持期限で本文を削除 |
| Reaction Roleの監査 | Role操作の記録。保持期間の既定値は90日 |

DB Backupには個人情報や認証情報が含まれます。Host外での保管は暗号化し、復号鍵と保管先のアクセスを管理します。

## ログと外部サービス

アプリログでは時刻、サービス名、イベント種別、コード位置、HTTPステータス、例外型を確認できます。[監視手順](monitoring.md)に従って調査します。

Safe BrowsingはURLの脅威確認に必要な情報を外部サービスへ送信します。TikTok・Instagramの公開アカウント監視は公開情報を取得します。`/gemini` は利用者が送信した質問をGeminiへ渡します。利用する機能に応じて、入力内容と外部サービスの利用条件を確認してください。
