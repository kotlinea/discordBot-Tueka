# 症状から探す

| 症状 | 対応 |
| --- | --- |
| ログイン期限切れ（401） | 再ログインします。 |
| 権限不足（403） | Manage Server、担当Team、BotのRole階層とChannel権限を確認します。 |
| 他の管理者と競合（409） | 再読込し、差分を再適用します。古い値をそのまま再送しないでください。 |
| 入力エラー（422） | 表示されたField、必須項目、Channel・Roleの所属を確認します。 |
| Roleが付かない | Manage Roles、Role階層、Emoji、Lock、アクセス制限を確認します。管理者は `/reactionrole manage fix` を使用できます。 |
| 通知が届かない | 対象アカウントの実在、通知Channel、Bot権限を確認します。初回確認を基準に、それ以降の新着を通知します。 |
| Transcriptが開けない | 担当権限とリンクを確認し、Ticket ID・時刻を運用者へ伝えます。 |
| ページが表示されない・通知状態がoffline | 時刻、URL、Providerと表示内容を運用者へ伝えます。Tokenや個人のTicket本文は共有しないでください。 |

[権限ガイド](../guide/permissions)と[保存・競合](../dashboard/saving)も参照してください。
