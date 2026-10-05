# 権限診断

ダッシュボードは保存時と処置の実行直前にBot権限を検証します。権限不足が表示された場合は、Discordのサーバーロール、ロール階層、カテゴリとチャンネルごとの権限設定（Overwrite）を確認します。

| 症状 | 主に確認する権限 |
| --- | --- |
| メッセージを削除できない | Manage Messages、View Channel |
| ロールを付与できない | Manage Roles、ロール階層 |
| Timeoutできない | Moderate Members、ロール階層 |
| チャンネルを作成・Lockできない | Manage Channels |
| 非公開スレッドのチケットを作れない | Manage Threads、Create Private Threads、Send Messages in Threads |
| ログの実行者が不明 | View Audit Log |

Discord APIの一時障害や対象削除でも処理は失敗します。その場合は権限を変更せず、イベント詳細やOutboxのエラーを確認してください。
