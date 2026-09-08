# 実環境デプロイ確認 TODO

> 最新の正本は[Linux / VPS](./operations/linux.md)、[更新とロールバック](./operations/upgrade.md)、[環境変数](./reference/environment.md)です。この文書は1リリースだけ保持します。

このリポジトリ内の実装・ローカルテストは完了済みです。以下はVPS、公開ドメイン、Discord Developer Portalへのアクセスがある環境で実施します。

## 事前設定

- [ ] `.env` に新規発行済みの `DISCORD_TOKEN`、`DISCORD_CLIENT_SECRET`、`SESSION_SECRET` を設定する。秘密情報をGitへ追加しない。
- [ ] `DISCORD_REDIRECT_URI` を公開HTTPS URL（例: `https://bot.example.com/oauth/callback`）に設定し、Developer PortalのOAuth2 Redirectsにも**完全一致**で登録する。
- [ ] Developer Portalで Server Members Intent と Message Content Intent を有効化する。
- [ ] 必要に応じて `GOOGLE_SAFE_BROWSING_API_KEY` を設定し、Google Safe Browsing APIの利用条件を運用前に確認する。
- [ ] ソーシャル通知を使う場合は、必要な `YOUTUBE_API_KEY`、`TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET`、`X_BEARER_TOKEN` を設定する。TikTok／Instagramも使う場合は各OAuth設定と `SOCIAL_TOKEN_ENCRYPTION_KEY` を設定する。
- [ ] `DASHBOARD_BASE_URL` は公開HTTPSの正規URLにし、YouTube WebSub callback は `https://<domain>/webhooks/youtube`、TikTok／Instagram Redirect URI は各 callback URL としてプロバイダ側へ完全一致で登録する。

## VPS・HTTPS

- [ ] `migrate_json.py` を一度だけ実行する。
- [ ] `tueka-bot` と `tueka-dashboard` をsystemdサービスとして起動する。
- [ ] Nginxのドメイン・証明書設定を実環境用に置き換え、HTTPSでダッシュボードへ到達できることを確認する。
- [ ] `systemctl status tueka-bot tueka-dashboard` と各サービスのログで、個別再起動後も正常であることを確認する。

## OAuth・認可

- [ ] 公開URLからDiscord OAuth2ログインし、コールバック後に `/servers` へ遷移することを確認する。
- [ ] Bot導入済みかつAdministrator権限を持つサーバーだけが表示されることを確認する。
- [ ] ログアウト後および期限切れセッションで管理画面が拒否されることを確認する。

## 機能別確認

- [ ] ダッシュボードで機能を有効化し、必要なBot権限がない場合は不足表示・保存拒否となることを確認する。
- [ ] 制裁、チャットフィルター、スパム対策、リアクションロールをテスト用サーバーで確認する。
- [ ] ライブ統計VC、一時VC、チケット作成・クローズ・議事録、投票、信頼度スコアをテスト用サーバーで確認する。
