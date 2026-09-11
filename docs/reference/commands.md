# コマンドリファレンス

`/help`は現在利用できるApplication Commandを表示します。`all:true`は無効機能を含む全Commandを表示します。詳しい設定はDashboardを使用します。

## 基本

| Command | 説明 | 応答 |
| --- | --- | --- |
| `/help [all]` | Command一覧 | `all:false`は実行者のみ |
| `/ping` | Bot Latency | 公開 |
| `/echo` | Title、Description、画像、最大25 FieldsのEmbed作成 | `ephemeral`選択可 |
| `/calculate expression` | `+ - * / % **`の安全な計算 | Errorは実行者のみ |
| `/roll [sides]` | 1～1,000,000面 | 公開 |
| `/userinfo [member]` | User、Role、参加日など | 公開 |
| `/serverinfo` | Server情報 | 公開 |
| `/gemini` | Geminiへ質問 | API Key設定時 |

## レベリング・コミュニティ

| Command | 説明 |
| --- | --- |
| `/rank` / `/leaderboard` | Text XPの本人情報／順位 |
| `/vcrank` / `/vcleaderboard` | Voice XPの本人情報／順位 |
| `/welcome` | Welcome Messageを手動送信 |
| `/poll` | 最大10択のButton投票 |
| `/suggest` | 本人だけに表示されるフォームから提案を投稿 |
| `/rps` | じゃんけん |
| `/trust_score` / `/clear_trust_score` | Trust Score確認／手動解除 |

## Moderation

管理権限とRole階層を実行時に確認します。理由はCaseとLogへ保存されます。

- `/mod warn`、`/mod timeout`、`/mod untimeout`
- `/mod kick`、`/mod ban`、`/mod softban`、`/mod unban`
- `/mod purge`、`/mod lock`、`/mod unlock`
- `/mod lockdown`、`/mod unlockdown`
- 互換Command：`/warn`、`/timeout`、`/kick`、`/ban`、`/clear`
- 管理Channel：`/set_management`

## Ticket

- `/ticket open`、`claim`、`unclaim`、`transfer`
- `/ticket add`、`remove`、`rename`、`switch-panel`
- `/ticket notes`、`tag`、`join`、`on-call`
- `/ticket close`、`close-request`、`reopen`
- `/ticket blacklist`、`setup`、`stats`
- 短縮：`/t open`、`/t close`

Thread ModeではClaimとNotesではなくJoin／On-Callを使用します。ReopenはArchive済みThread Ticketだけが対象です。

## Reaction Roles

- 作成・対応：`/reactionrole create`、`add`、`addmany`、`remove`、`purge`、`aio`、`channel`
- 変更：`/reactionrole modify type`、`limit`、`maxroles`、`lock`、`unlock`
- Access：`/reactionrole whitelist add|remove|clear`、`blacklist add|remove|clear`
- Link：`/reactionrole link create|list|unlink`
- 保守：`/reactionrole manage show|fix|fixforeign|edit|color|move|selfdestruct|reset-binding`
- 短縮：`/r add|addmany|remove|show|fix|aio|aiou|aiov|aioi|normal|unique|verify|binding|drop|reversed|temp|lock|unlock`
- Legacy Panel：`/publish_reaction_roles`

`addmany`とAIOの複数対応はModalへ1行ずつ入力します。PurgeとSelfdestructは対象Messageと復旧可能性を確認して実行してください。
