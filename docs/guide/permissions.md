# 必要な権限

メンバーは各コマンドの権限を確認してください。サーバー管理者はBotの権限とRole階層を確認します。接続自体の問題はシステム運用者へ連絡してください。

## Bot権限

| 権限 | 主な用途 |
| --- | --- |
| View Channel / Send Messages | 通知、ログ、Panel、通常応答 |
| Embed Links / Attach Files | Embed、Ticket Transcript、添付 |
| Read Message History | Ticket、Reaction Roles、ログ |
| Manage Messages | AutoMod削除、Purge、リアクション除去 |
| Manage Roles | Auto Role、Reaction Roles |
| Moderate Members | Timeout |
| Kick Members / Ban Members | Kick、Ban、Tempban、Anti-Raid |
| Manage Channels | Lock、Lockdown、一時VC、Ticket Channel |
| Manage Threads / Create Private Threads / Send Messages in Threads | Thread Mode Ticket |
| Move Members | 一時VCへの移動 |
| View Audit Log | 管理操作の実行者突合 |

## Role階層

Manage RolesやBan権限を持っていても、Botの最上位Role以上のRole・Memberは操作できません。BotのRoleを、付与対象Roleと処置対象Memberの最上位Roleより上へ移動します。

チャンネルOverwriteはサーバー権限を上書きします。Dashboardの権限診断が正常でも特定チャンネルだけ失敗する場合は、そのチャンネルとCategoryのOverwriteを確認してください。
