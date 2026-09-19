# 環境変数

値は`.env`またはProcess Managerから設定します。秘密値をGitへCommitしないでください。

## 基本・Dashboard

| 変数 | 必須・既定値 | Process | 内容 |
| --- | --- | --- | --- |
| `DISCORD_TOKEN` | 必須 | 全Process | Discord Bot Token。秘密 |
| `DISCORD_CLIENT_ID` | Dashboard必須 | Dashboard | OAuth Application ID |
| `DISCORD_CLIENT_SECRET` | Dashboard必須 | Dashboard | OAuth Secret。秘密 |
| `DISCORD_REDIRECT_URI` | Dashboard必須 | Dashboard | Developer Portalと完全一致するCallback |
| `SESSION_SECRET` | Dashboard必須 | Dashboard | Session署名鍵。秘密 |
| `DASHBOARD_BASE_URL` | 公開機能で推奨 | 全Process | 例：`https://bot.example.com` |
| `BOT_INVITE_URL` | 空 | 未使用 | `.env.example` に存在するが、現在のRuntimeには読取り処理がない。設定しても招待先は変わらない。 |
| `DASHBOARD_HTTPS_ONLY` | `true` | Dashboard | Secure Cookieを要求 |
| `DATA_DIR` | `data` | 全Process | Data Directory |
| `DATABASE_URL` | 必須 | 全Process | 共通PostgreSQL接続URL。秘密値として管理 |
| `LOG_LEVEL` | `INFO` | 全Process | Log Level |

変更後は対象Processを再起動します。OAuth URLを変更した場合はDiscord Developer Portalも更新します。

## API・Moderation

| 変数 | 必須・既定値 | 内容 |
| --- | --- | --- |
| `GEMINI_API_KEY` | 任意 | `/gemini`用。秘密 |
| `GEMINI_MODEL` | `gemini-2.5-flash` | 使用Model |
| `GOOGLE_SAFE_BROWSING_API_KEY` | Safe Browsing使用時 | URL脅威照会。秘密 |

## Social

| 変数 | 既定値 | 内容 |
| --- | --- | --- |
| `YOUTUBE_API_KEY` | 空 | Channel解決、Uploads Playlist、Live状態補完 |
| `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` | 空 | EventSubとApp Token。Secretは秘密 |
| `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET` / `TIKTOK_REDIRECT_URI` | 空 | TikTok OAuth |
| `INSTAGRAM_APP_ID` / `INSTAGRAM_APP_SECRET` / `INSTAGRAM_REDIRECT_URI` | 空 | Instagram OAuth |
| `X_BEARER_TOKEN` | 空 | X API。秘密 |
| `SOCIAL_TOKEN_ENCRYPTION_KEY` | 空 | OAuth Token暗号化鍵。秘密 |
| `SOCIAL_WEBHOOK_SECRET` | 必須 | Webhook検証鍵。秘密 |
| `SOCIAL_X_MODE` | `stream` | `stream`または`poll` |
| `SOCIAL_MAX_SUBSCRIPTIONS_PER_PROVIDER` | `10` | 1 Guild・1 Providerの上限。1～100 |
| `SOCIAL_POLL_INTERVAL_SECONDS` | `120` | 基本Polling間隔。30～3600秒 |
| `INSTAGRAM_RSS_URL_TEMPLATE` | 空 | `{account}`を含む運用者管理URL |
| `INSTAGRAM_RSS_AUTH_TOKEN` | 空 | 外部RSS認証。秘密 |

Provider資格情報を変更した場合はDashboardとSocial Workerを再起動します。

## Ticket

| 変数 | 既定値 | 内容 |
| --- | --- | --- |
| `TICKET_ENCRYPTION_KEY` | 空 | Transcript、回答、Noteの暗号鍵。秘密 |
| `TICKET_S3_ENDPOINT_URL` | 空 | S3互換Endpoint |
| `TICKET_S3_REGION` | 空 | Region |
| `TICKET_S3_BUCKET` | 空 | Bucket |
| `TICKET_S3_ACCESS_KEY_ID` / `TICKET_S3_SECRET_ACCESS_KEY` | 空 | S3 Credential。秘密 |
| `TICKET_S3_PREFIX` | `ticket-transcripts` | Object Prefix |

暗号鍵を変更すると既存Blobを復号できなくなります。Rotationは移行手順を用意してから実施します。

## Reaction Roles

| 変数 | 既定値 | 内容 |
| --- | --- | --- |
| `REACTION_ROLE_MAX_MAPPINGS_PER_MESSAGE` | `20` | 1 MessageのEmoji→Role対応上限。1～100 |

## コンテナの実行設定

| 変数 | 既定値 | 内容 |
| --- | --- | --- |
| `MONITORING_TOKEN` | 空 | 内部メトリクスの専用Bearer Token。32文字以上。未設定時は公開しない。秘密 |
| `HEARTBEAT_MAX_AGE_SECONDS` | `30` | HTTP/CLI集計のHeartbeat許容秒。5～3600 |
| `OUTBOX_MAX_AGE_SECONDS` | `300` | 期限超過Queueの遅延閾値。1～86400 |

設定方法・初期閾値とStage判定は[監視と障害対応](../operations/monitoring)を参照してください。

環境別Composeは`TUEKA_ENV_FILE=/run/secrets/app_env`を指定し、明示した秘密ファイルだけを読み込みます。ファイルがなければ起動を拒否し、ソースの.envへfallbackしません。既に注入された環境変数を上書きせず、秘密ファイル内の変数展開を無効にします。

Imageは`TUEKA_FRONTEND_DIST=/opt/tueka-assets/ui`と`TUEKA_DOCS_DIST=/opt/tueka-assets/docs`を設定します。Devのソースmountからビルド済み資産を分離するための設定で、Host起動では未指定のまま従来のdistを使用できます。`DATA_DIR`はComposeが`/data`へ固定します。

Project/Image/Portと環境専用の接続秘密の生成・検査は[環境別Compose](../operations/compose)を参照してください。
