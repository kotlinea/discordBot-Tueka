# セキュリティとプライバシー

## 認証と更新

DashboardはDiscord OAuth、Session Cookie、CSRF Header、Manage Guild確認を使用します。全更新で権限を再確認し、他GuildのChannel、Role、Emoji IDを拒否します。

Session CookieはHTTPS環境でSecureにします。`SESSION_SECRET`は十分に長い乱数とし、共有しません。

## 秘密情報

Discord Token、OAuth Secret、SNS API Key、Webhook Secret、暗号鍵、S3 Credentialは環境変数だけで管理します。ログ、Docs、Export JSON、Dashboard Payloadへ含めません。

## 保存データ

- Moderation本文証跡：最大1000文字。機密Channel除外と保持期限あり
- Social Event：正規化Metadata。完了履歴は30日
- Ticket本文・Form回答・Note・Transcript：暗号化。保持期限後に本文を削除
- Reaction Role監査：Message本文を保存せず、既定90日

SQLite、Backup、暗号化前の一時FileへOS権限を設定します。暗号化はHost侵害や復号鍵漏えいを防ぐものではありません。

## 外部送信

Safe BrowsingにはURL脅威確認に必要な情報だけを送ります。本文や画像を外部AI分類へ送信しません。TikTokとInstagramの非公式Adapterは公開情報だけを取得します。
