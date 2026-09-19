# Discord ApplicationとOAuth

1. Discord Developer Portalで専用ApplicationとBotを作成します。Dev/Stage/本番の資格情報は分離します。
2. Bot TokenとOAuth Client ID/Secretを生成し、configureで用意した私有app.envへローカルエディタで設定します。Git・コマンド引数・ログへ出力しません。
3. 公開originをDASHBOARD_BASE_URLへ、同じoriginの `/oauth/callback` をDISCORD_REDIRECT_URIへ設定します。Developer PortalのRedirectsにも完全一致で登録します。
4. Server Members、Message Content、Presenceなどコードが要求するGateway IntentをPortalで確認します。利用できないIntentはBot接続障害の原因になります。
5. botとapplications.commandsのスコープで招待リンクを作成し、[利用者の権限一覧](../../docs/guide/permissions.md)に従ってBotを専用Guildへ招待します。Administratorを一律に付与しません。
6. [導入フロー](setup.md)でbuild/startし、専用Guildでログイン・コマンド・権限不足を受入します。

Ticket暗号鍵とSocial Token暗号鍵は[環境変数](environment.md)を参照し、保管先とBackupを用意します。既存鍵の単純な置換は暗号化データを読めなくするため禁止です。
