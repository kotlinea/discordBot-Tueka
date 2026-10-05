# 必要な権限

メンバーは各コマンドの権限を確認してください。サーバー管理者はBotの権限とロール階層を確認します。接続自体の問題はシステム運用者へ連絡してください。

## Bot権限

| 権限 | 主な用途 |
| --- | --- |
| View Channel / Send Messages | 通知、ログ、パネル、通常応答 |
| Embed Links / Attach Files | Embed、チケットの対応履歴、添付 |
| Read Message History | チケット、リアクションロール、ログ |
| Manage Messages | AutoMod削除、Purge、リアクション除去 |
| Manage Roles | 初期ロール、リアクションロール |
| Moderate Members | Timeout |
| Kick Members / Ban Members | Kick、Ban、Tempban、Anti-Raid |
| Manage Channels | Lock、Lockdown、一時VC、チケット用チャンネル |
| Manage Threads / Create Private Threads / Send Messages in Threads | スレッド方式のチケット |
| Move Members | 一時VCへの移動 |
| View Audit Log | 管理操作を行った人の確認 |

## ロール階層

Manage RolesやBan権限を持っていても、Botの最上位ロール以上のロール・メンバーは操作できません。Botのロールを、付与対象ロールと処置対象メンバーの最上位ロールより上へ移動します。

チャンネルごとの権限設定（Overwrite）はサーバー権限を上書きします。ダッシュボードの権限診断が正常でも特定チャンネルだけ失敗する場合は、そのチャンネルとカテゴリの権限設定を確認してください。
