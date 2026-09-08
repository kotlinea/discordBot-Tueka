# 権限診断

Dashboardは保存時とAction実行直前にBot権限を検証します。権限不足が表示された場合は、DiscordのサーバーRole、Role階層、CategoryとChannelのOverwriteを確認します。

| 症状 | 主に確認する権限 |
| --- | --- |
| メッセージを削除できない | Manage Messages、View Channel |
| Roleを付与できない | Manage Roles、Role階層 |
| Timeoutできない | Moderate Members、Role階層 |
| Channelを作成・Lockできない | Manage Channels |
| Private Thread Ticketを作れない | Manage Threads、Create Private Threads、Send Messages in Threads |
| ログの実行者が不明 | View Audit Log |

Discord APIの一時障害や対象削除でも処理は失敗します。その場合は権限を変更せず、イベント詳細やOutboxのエラーを確認してください。
