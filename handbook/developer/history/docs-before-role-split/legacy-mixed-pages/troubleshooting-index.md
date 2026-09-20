# 症状から探す

## 保存すると未設定へ戻る

1. BrowserのNetworkでPUT／POSTのStatusを確認します。
2. 422ならResponseの`errors[].path`に対応するFieldを修正します。
3. 選択したChannel／Roleが同じGuildに存在するか確認します。
4. 必須Field、Bot権限、Role階層を確認します。
5. 409なら再読込して最新revisionを取得します。

古いTabの値をそのまま再送しないでください。

## 401／403／409／422

| Status | 原因 | 対応 |
| --- | --- | --- |
| 401 | Session期限切れ | 再ログイン |
| 403 | Manage Guild、Staff権限、CSRF不足 | 権限とSessionを確認 |
| 409 | 他の管理者が更新 | 再読込して差分を再適用 |
| 422 | 値、Resource、組み合わせが無効 | Field Errorのpathを修正 |

## リアクションしてもRoleが付かない

Manage Roles、Add Reactions、Read Message History、Manage Messages、View ChannelとRole階層を確認します。次にLock、Access方式、Binding履歴、Limit、Max Roles、Emoji対応を確認し、`/reactionrole manage fix`を実行します。

## YouTube RSSが404になる

登録対象が実在するChannel IDか確認します。正しいFeed形式は`https://www.youtube.com/feeds/videos.xml?channel_id=UC...`です。それでも404になる場合はYouTube側のFeed状態です。WorkerはChannel Pageを再確認し、API KeyがあればUploads Playlist API、なければ`yt-dlp`による動画一覧へFallbackします。Errorが連続するとRSS Circuitを開きます。

## Social Workerがdegraded／offline

Process、Heartbeat、Provider資格情報、429、Timeout、次回実行時刻を確認します。`DATABASE_URL`がBot／Dashboardと一致していることも確認します。1 ProviderのCircuit Breakerは他Providerを停止しません。

## Ticket Transcriptを作成できない

`TICKET_ENCRYPTION_KEY`、Disk容量、Directory権限、Read Message History、Attach Filesを確認します。S3使用時はEndpoint、Bucket、Credential、Object Prefixを確認します。S3失敗時は暗号化LocalへFallbackするため、Outboxの再送状態も確認します。

## Discord処置が権限不足になる

Server Role権限だけでなく、Bot Roleの位置、対象Memberの最上位Role、Category／Channel Overwriteを確認します。OwnerとBot以上のMemberは操作できません。

## Dashboardが404になる

React UIは`dashboard/frontend`、Docsは`docs`でBuildします。`dashboard/frontend/dist/index.html`と`docs/.vitepress/dist/index.html`が存在することを確認し、Dashboardを再起動します。
