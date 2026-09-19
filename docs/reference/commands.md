# 全Discordコマンド

引数の名前・型と必須条件は実登録と照合しています。IDや対象は実際のサーバーの値へ置き換えてください。処置・削除の例は検証用サーバーだけで試してください。

## /ban

- **用途**: メンバーを追放します。
- **引数（*必須）**: member*:user, reason:string
- **権限**: ban_members; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/ban member:@TestMember`

## /calculate

- **用途**: 四則演算と累乗を計算します。
- **引数（*必須）**: expression*:string
- **権限**: 一般メンバー（サーバーとChannelの利用権限が必要）。
- **応答**: 公開応答。エラーは本人向け。
- **無効時**: 基本コマンド。権限・実行場所などの条件は引き続き適用。
- **例**: `/calculate expression:2+3*4`

## /clear

- **用途**: このチャネルのメッセージを削除します。
- **引数（*必須）**: confirm:string
- **権限**: manage_messages; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/clear confirm:confirm`

## /clear_trust_score

- **用途**: メンバーの信頼度イベントを手動で解除します。制裁履歴は残ります。
- **引数（*必須）**: member*:user
- **権限**: manage_guild; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/clear_trust_score member:@TestMember`

## /echo

- **用途**: 自由にEmbedを組み立てて送信します。
- **引数（*必須）**: title:string, description:string, color:string, url:string, author_name:string, author_url:string, author_icon_url:string, footer_text:string, footer_icon_url:string, thumbnail_url:string, image_url:string, fields_json:string, timestamp:boolean = false, ephemeral:boolean = false
- **権限**: 一般メンバー（サーバーとChannelの利用権限が必要）。
- **応答**: ephemeral引数で本人向け／公開を選択。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/echo`

## /gemini

- **用途**: Gemini APIから質問します。
- **引数（*必須）**: message*:string
- **権限**: 一般メンバー（サーバーとChannelの利用権限が必要）。
- **応答**: 応答と生成エラーは公開。未設定時の案内は本人向け。
- **無効時**: システム運用者が利用可能にしていない場合は質問できません。
- **例**: `/gemini message:Hello`

## /help

- **用途**: 利用できるコマンド一覧を表示します。
- **引数（*必須）**: all:boolean = false
- **権限**: 一般メンバー（サーバーとChannelの利用権限が必要）。
- **応答**: all:falseは本人向け、all:trueは公開。
- **無効時**: 基本コマンド。権限・実行場所などの条件は引き続き適用。
- **例**: `/help`

## /kick

- **用途**: メンバーをキックします。
- **引数（*必須）**: member*:user, reason:string
- **権限**: kick_members; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/kick member:@TestMember`

## /leaderboard

- **用途**: テキストXPランキングを表示します。
- **引数（*必須）**: —
- **権限**: 一般メンバー（サーバーとChannelの利用権限が必要）。
- **応答**: 公開応答。エラーは本人向け。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/leaderboard`

## /mod ban

- **用途**: メンバーをBanします。
- **引数（*必須）**: member*:user, reason:string
- **権限**: ban_members; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/mod ban member:@TestMember`

## /mod kick

- **用途**: メンバーをKickします。
- **引数（*必須）**: member*:user, reason:string
- **権限**: kick_members; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/mod kick member:@TestMember`

## /mod lock

- **用途**: チャンネルをロックします。
- **引数（*必須）**: channel:channel, reason:string
- **権限**: manage_channels; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/mod lock`

## /mod lockdown

- **用途**: サーバーを期限付きでLockdownします。
- **引数（*必須）**: minutes:integer [1..1440] = 30, reason:string
- **権限**: administrator; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/mod lockdown`

## /mod purge

- **用途**: 最近のメッセージを削除します。
- **引数（*必須）**: count*:integer [1..100], reason:string
- **権限**: manage_messages; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/mod purge count:1`

## /mod softban

- **用途**: メンバーをSoftbanします。
- **引数（*必須）**: member*:user, reason:string
- **権限**: ban_members; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/mod softban member:@TestMember`

## /mod timeout

- **用途**: Timeoutを設定します。
- **引数（*必須）**: member*:user, minutes*:integer [1..40320], reason:string
- **権限**: moderate_members; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/mod timeout member:@TestMember minutes:5`

## /mod unban

- **用途**: ユーザーIDを指定してBanを解除します。
- **引数（*必須）**: user_id*:string, reason:string
- **権限**: ban_members; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/mod unban user_id:123456789012345678`

## /mod unlock

- **用途**: チャンネルのロックを解除します。
- **引数（*必須）**: channel:channel, reason:string
- **権限**: manage_channels; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/mod unlock`

## /mod unlockdown

- **用途**: 有効なLockdownを解除します。
- **引数（*必須）**: reason:string
- **権限**: administrator; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/mod unlockdown`

## /mod untimeout

- **用途**: Timeoutを解除します。
- **引数（*必須）**: member*:user, reason:string
- **権限**: moderate_members; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/mod untimeout member:@TestMember`

## /mod warn

- **用途**: Warningを追加します。
- **引数（*必須）**: member*:user, reason:string
- **権限**: moderate_members; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/mod warn member:@TestMember`

## /ping

- **用途**: Botの応答速度を計測します。
- **引数（*必須）**: —
- **権限**: 一般メンバー（サーバーとChannelの利用権限が必要）。
- **応答**: 公開応答。エラーは本人向け。
- **無効時**: 基本コマンド。権限・実行場所などの条件は引き続き適用。
- **例**: `/ping`

## /poll

- **用途**: 最大10択のボタン投票を作成します。選択肢は | で区切ります。
- **引数（*必須）**: question*:string, options*:string, duration_minutes:integer [1..10080], image_url:string
- **権限**: manage_guild; Bot permissions and role hierarchy also apply.
- **応答**: 公開応答。エラーは本人向け。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/poll question:Lunch? options:A|B`

## /r add

- **用途**: 短縮コマンド。EmojiとRoleの対応を追加します。
- **引数（*必須）**: config_id*:integer, emoji*:string, role*:role
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/r add config_id:1 emoji:✅ role:@TestRole`

## /r addmany

- **用途**: 短縮コマンド。フォームから複数のEmojiとRole対応を追加します。
- **引数（*必須）**: config_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/r addmany config_id:1`

## /r aio

- **用途**: 短縮コマンド。投稿と対応を一括作成します。
- **引数（*必須）**: channel*:channel, emoji*:string, role*:role
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/r aio channel:#test emoji:✅ role:@TestRole`

## /r aioi

- **用途**: 短縮コマンド。binding方式で投稿と対応を一括作成します。
- **引数（*必須）**: channel*:channel, emoji*:string, role*:role
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/r aioi channel:#test emoji:✅ role:@TestRole`

## /r aiou

- **用途**: 短縮コマンド。unique方式で投稿と対応を一括作成します。
- **引数（*必須）**: channel*:channel, emoji*:string, role*:role
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/r aiou channel:#test emoji:✅ role:@TestRole`

## /r aiov

- **用途**: 短縮コマンド。verify方式で投稿と対応を一括作成します。
- **引数（*必須）**: channel*:channel, emoji*:string, role*:role
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/r aiov channel:#test emoji:✅ role:@TestRole`

## /r binding

- **用途**: 短縮コマンド。binding方式へ変更します。
- **引数（*必須）**: config_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/r binding config_id:1`

## /r drop

- **用途**: 短縮コマンド。drop方式へ変更します。
- **引数（*必須）**: config_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/r drop config_id:1`

## /r fix

- **用途**: 短縮コマンド。Messageのリアクションと設定を再同期します。
- **引数（*必須）**: config_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/r fix config_id:1`

## /r lock

- **用途**: 短縮コマンド。Role変更を停止します。
- **引数（*必須）**: config_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/r lock config_id:1`

## /r normal

- **用途**: 短縮コマンド。normal方式へ変更します。
- **引数（*必須）**: config_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/r normal config_id:1`

## /r remove

- **用途**: 短縮コマンド。Roleの対応を削除します。
- **引数（*必須）**: config_id*:integer, role*:role
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/r remove config_id:1 role:@TestRole`

## /r reversed

- **用途**: 短縮コマンド。reversed方式へ変更します。
- **引数（*必須）**: config_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/r reversed config_id:1`

## /r show

- **用途**: 短縮コマンド。設定を表示します。
- **引数（*必須）**: config_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/r show config_id:1`

## /r temp

- **用途**: 短縮コマンド。期限付きRoleへ変更します。
- **引数（*必須）**: config_id*:integer, minutes*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/r temp config_id:1 minutes:5`

## /r unique

- **用途**: 短縮コマンド。unique方式へ変更します。
- **引数（*必須）**: config_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/r unique config_id:1`

## /r unlock

- **用途**: 短縮コマンド。Role変更を再開します。
- **引数（*必須）**: config_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/r unlock config_id:1`

## /r verify

- **用途**: 短縮コマンド。verify方式へ変更します。
- **引数（*必須）**: config_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/r verify config_id:1`

## /rank

- **用途**: 現在のテキストレベルを確認します。
- **引数（*必須）**: —
- **権限**: 一般メンバー（サーバーとChannelの利用権限が必要）。
- **応答**: 公開応答。エラーは本人向け。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/rank`

## /reactionrole add

- **用途**: EmojiとRoleの対応を追加します
- **引数（*必須）**: config_id*:integer, emoji*:string, role*:role
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole add config_id:1 emoji:✅ role:@TestRole`

## /reactionrole addmany

- **用途**: 複数のEmojiとRoleをまとめて追加します
- **引数（*必須）**: config_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole addmany config_id:1`

## /reactionrole aio

- **用途**: 投稿とEmoji→Role対応を一括作成します
- **引数（*必須）**: channel*:channel, emoji*:string, role*:role, behavior:string = "normal", title:string = "ロールを選択"
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole aio channel:#test emoji:✅ role:@TestRole`

## /reactionrole blacklist add

- **用途**: 対象Roleをリストへ追加します。
- **引数（*必須）**: config_id*:integer, role*:role
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole blacklist add config_id:1 role:@TestRole`

## /reactionrole blacklist clear

- **用途**: 対象リストを空にします。
- **引数（*必須）**: config_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole blacklist clear config_id:1`

## /reactionrole blacklist remove

- **用途**: 対象Roleをリストから削除します。
- **引数（*必須）**: config_id*:integer, role*:role
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole blacklist remove config_id:1 role:@TestRole`

## /reactionrole channel

- **用途**: Reaction Roles専用チャンネルを作成します
- **引数（*必須）**: name:string = "roles"
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole channel`

## /reactionrole create

- **用途**: Bot投稿または既存メッセージへReaction Rolesを作成します
- **引数（*必須）**: channel*:channel, emoji*:string, role*:role, title:string = "ロールを選択", message_id:string
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole create channel:#test emoji:✅ role:@TestRole`

## /reactionrole link create

- **用途**: メッセージのLinkグループを作成します。
- **引数（*必須）**: name*:string, message_ids*:string
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole link create name:test message_ids:123456789012345678`

## /reactionrole link list

- **用途**: Linkグループを一覧表示します。
- **引数（*必須）**: —
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole link list`

## /reactionrole link unlink

- **用途**: Linkを解除します。
- **引数（*必須）**: group_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole link unlink group_id:1`

## /reactionrole manage color

- **用途**: Embed色を変更します。
- **引数（*必須）**: config_id*:integer, color*:string
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole manage color config_id:1 color:#336699`

## /reactionrole manage edit

- **用途**: Embedを編集します。
- **引数（*必須）**: config_id*:integer, title*:string, description:string = ""
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole manage edit config_id:1 title:Test`

## /reactionrole manage fix

- **用途**: 設定を修復します。
- **引数（*必須）**: config_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole manage fix config_id:1`

## /reactionrole manage fixforeign

- **用途**: 外部絵文字のリアクションロール設定を修復します。
- **引数（*必須）**: config_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole manage fixforeign config_id:1`

## /reactionrole manage move

- **用途**: 設定先Messageを変更します。
- **引数（*必須）**: config_id*:integer, channel*:channel, message_id*:string
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole manage move config_id:1 channel:#test message_id:123456789012345678`

## /reactionrole manage reset-binding

- **用途**: 利用者のBinding記録を解除します。
- **引数（*必須）**: config_id*:integer, user*:user
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole manage reset-binding config_id:1 user:@TestMember`

## /reactionrole manage selfdestruct

- **用途**: 設定の削除を予約します。
- **引数（*必須）**: config_id*:integer, minutes*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole manage selfdestruct config_id:1 minutes:5`

## /reactionrole manage show

- **用途**: 設定を表示します。
- **引数（*必須）**: config_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole manage show config_id:1`

## /reactionrole modify limit

- **用途**: ユーザーごとの選択上限を変更します
- **引数（*必須）**: config_id*:integer, limit*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole modify limit config_id:1 limit:1`

## /reactionrole modify lock

- **用途**: Role変更を停止します
- **引数（*必須）**: config_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole modify lock config_id:1`

## /reactionrole modify maxroles

- **用途**: Roleの実人数上限を変更します
- **引数（*必須）**: config_id*:integer, role*:role, maximum*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole modify maxroles config_id:1 role:@TestRole maximum:10`

## /reactionrole modify type

- **用途**: 動作Typeを変更します
- **引数（*必須）**: config_id*:integer, behavior*:string (binding, drop, normal, reversed, temp, unique, verify), duration_minutes:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole modify type config_id:1 behavior:normal`

## /reactionrole modify unlock

- **用途**: Role変更を再開します
- **引数（*必須）**: config_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole modify unlock config_id:1`

## /reactionrole purge

- **用途**: Reaction Role設定を削除します
- **引数（*必須）**: config_id:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole purge`

## /reactionrole remove

- **用途**: Roleの対応を削除します
- **引数（*必須）**: config_id*:integer, role*:role
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole remove config_id:1 role:@TestRole`

## /reactionrole whitelist add

- **用途**: 対象Roleをリストへ追加します。
- **引数（*必須）**: config_id*:integer, role*:role
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole whitelist add config_id:1 role:@TestRole`

## /reactionrole whitelist clear

- **用途**: 対象リストを空にします。
- **引数（*必須）**: config_id*:integer
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole whitelist clear config_id:1`

## /reactionrole whitelist remove

- **用途**: 対象Roleをリストから削除します。
- **引数（*必須）**: config_id*:integer, role*:role
- **権限**: サーバー管理（Manage Server）。BotのManage RolesとRole階層も必要。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/reactionrole whitelist remove config_id:1 role:@TestRole`

## /roll

- **用途**: 指定された乱数を振ります。
- **引数（*必須）**: sides:number = 6.0
- **権限**: 一般メンバー（サーバーとChannelの利用権限が必要）。
- **応答**: 公開応答。エラーは本人向け。
- **無効時**: 基本コマンド。権限・実行場所などの条件は引き続き適用。
- **例**: `/roll`

## /rps

- **用途**: じゃんけんでBotと対戦します。
- **引数（*必須）**: hand*:string (rock, paper, scissors)
- **権限**: 一般メンバー（サーバーとChannelの利用権限が必要）。
- **応答**: 公開応答。エラーは本人向け。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/rps hand:rock`

## /serverinfo

- **用途**: サーバー情報を表示します。
- **引数（*必須）**: —
- **権限**: 一般メンバー（サーバーとChannelの利用権限が必要）。
- **応答**: 公開応答。エラーは本人向け。
- **無効時**: 基本コマンド。権限・実行場所などの条件は引き続き適用。
- **例**: `/serverinfo`

## /set_management

- **用途**: サーバーログチャネルを設定します。
- **引数（*必須）**: channel*:channel
- **権限**: manage_guild; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/set_management channel:#test`

## /suggest

- **用途**: サーバーへアイデアや改善案を投稿します。
- **引数（*必須）**: —
- **権限**: 一般メンバー（サーバーとChannelの利用権限が必要）。
- **応答**: フォームと確認は本人向け、送信した提案は設定Channelへ公開。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/suggest`

## /t close

- **用途**: TicketをCloseします。
- **引数（*必須）**: reason:string = "解決済み"
- **権限**: 作成はPanelの受付・アクセス条件、Closeは作成者またはStaff（PanelのClose方針に従う）。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 受付無効は新規作成を停止します。既存Ticket操作は各コマンドの権限・状態条件に従います。
- **例**: `/t close`

## /t open

- **用途**: Ticketを作成します。
- **引数（*必須）**: panel_id*:integer
- **権限**: 作成はPanelの受付・アクセス条件、Closeは作成者またはStaff（PanelのClose方針に従う）。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/t open panel_id:1`

## /ticket add

- **用途**: Ticketへユーザーを追加します。
- **引数（*必須）**: member*:user
- **権限**: Ticket担当Staff／設定権限。現在のPanel・Team・Ticketへのアクセスを確認。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 受付無効は新規作成を停止します。既存Ticket操作は各コマンドの権限・状態条件に従います。
- **例**: `/ticket add member:@TestMember`

## /ticket blacklist

- **用途**: ユーザーのTicket作成制限を変更します。
- **引数（*必須）**: member*:user, enabled*:boolean, reason:string = "管理者による制限"
- **権限**: サーバー管理権限（Manage Server）。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 受付無効は新規作成を停止します。既存Ticket操作は各コマンドの権限・状態条件に従います。
- **例**: `/ticket blacklist member:@TestMember enabled:true`

## /ticket claim

- **用途**: 現在のTicketをClaimします。
- **引数（*必須）**: —
- **権限**: Ticket担当Staff／設定権限。現在のPanel・Team・Ticketへのアクセスを確認。
- **応答**: Ticket内／実行Channelへの公開応答。失敗は本人向け。
- **無効時**: 受付無効は新規作成を停止します。既存Ticket操作は各コマンドの権限・状態条件に従います。
- **例**: `/ticket claim`

## /ticket close

- **用途**: TicketをCloseしてTranscriptを保存します。
- **引数（*必須）**: reason:string = "解決済み"
- **権限**: 作成はPanelの受付・アクセス条件、Closeは作成者またはStaff（PanelのClose方針に従う）。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 受付無効は新規作成を停止します。既存Ticket操作は各コマンドの権限・状態条件に従います。
- **例**: `/ticket close`

## /ticket close-request

- **用途**: StaffへCloseの承認を依頼します。
- **引数（*必須）**: reason:string = "解決済み"
- **権限**: 現在のTicket内で実行可能。承認・却下は担当Staff。
- **応答**: Ticket内への公開応答。失敗は本人向け。
- **無効時**: 受付無効は新規作成を停止します。既存Ticket操作は各コマンドの権限・状態条件に従います。
- **例**: `/ticket close-request`

## /ticket join

- **用途**: Thread TicketへStaffとして参加します。
- **引数（*必須）**: ticket_id*:integer
- **権限**: Ticket担当Staff／設定権限。現在のPanel・Team・Ticketへのアクセスを確認。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 受付無効は新規作成を停止します。既存Ticket操作は各コマンドの権限・状態条件に従います。
- **例**: `/ticket join ticket_id:1`

## /ticket notes

- **用途**: 作成者には見えないStaff Noteを追加します。
- **引数（*必須）**: content*:string
- **権限**: Ticket担当Staff／設定権限。現在のPanel・Team・Ticketへのアクセスを確認。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 受付無効は新規作成を停止します。既存Ticket操作は各コマンドの権限・状態条件に従います。
- **例**: `/ticket notes content:Test note`

## /ticket on-call

- **用途**: Thread Ticketへの自動参加を切り替えます。
- **引数（*必須）**: team_id*:integer, enabled*:boolean
- **権限**: Ticket担当Staff／設定権限。現在のPanel・Team・Ticketへのアクセスを確認。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 受付無効は新規作成を停止します。既存Ticket操作は各コマンドの権限・状態条件に従います。
- **例**: `/ticket on-call team_id:1 enabled:true`

## /ticket open

- **用途**: Ticketを作成します。
- **引数（*必須）**: panel_id*:integer
- **権限**: 作成はPanelの受付・アクセス条件、Closeは作成者またはStaff（PanelのClose方針に従う）。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/ticket open panel_id:1`

## /ticket remove

- **用途**: Ticketからユーザーを削除します。
- **引数（*必須）**: member*:user
- **権限**: Ticket担当Staff／設定権限。現在のPanel・Team・Ticketへのアクセスを確認。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 受付無効は新規作成を停止します。既存Ticket操作は各コマンドの権限・状態条件に従います。
- **例**: `/ticket remove member:@TestMember`

## /ticket rename

- **用途**: Ticket名を変更します。
- **引数（*必須）**: name*:string
- **権限**: 現在のTicket Channel/Threadを参照できる利用者。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 受付無効は新規作成を停止します。既存Ticket操作は各コマンドの権限・状態条件に従います。
- **例**: `/ticket rename name:test`

## /ticket reopen

- **用途**: Closed Thread Ticketを再開します。
- **引数（*必須）**: ticket_id*:integer
- **権限**: Manage Threads。閉じた同一サーバーのThread Ticketが対象。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/ticket reopen ticket_id:1`

## /ticket setup

- **用途**: Ticket設定画面を開きます。
- **引数（*必須）**: —
- **権限**: サーバー管理権限（Manage Server）。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 受付無効は新規作成を停止します。既存Ticket操作は各コマンドの権限・状態条件に従います。
- **例**: `/ticket setup`

## /ticket stats

- **用途**: Ticketの概要を表示します。
- **引数（*必須）**: —
- **権限**: サーバー管理権限（Manage Server）。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 受付無効は新規作成を停止します。既存Ticket操作は各コマンドの権限・状態条件に従います。
- **例**: `/ticket stats`

## /ticket switch-panel

- **用途**: 同じModeの別Panelへ切り替えます。
- **引数（*必須）**: panel_id*:integer
- **権限**: Ticket担当Staff／設定権限。現在のPanel・Team・Ticketへのアクセスを確認。
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 受付無効は新規作成を停止します。既存Ticket操作は各コマンドの権限・状態条件に従います。
- **例**: `/ticket switch-panel panel_id:1`

## /ticket tag

- **用途**: 定型文を送信します。
- **引数（*必須）**: name*:string
- **権限**: サーバー内で登録済みTagを参照できる利用者。
- **応答**: Ticket内／実行Channelへの公開応答。失敗は本人向け。
- **無効時**: 受付無効は新規作成を停止します。既存Ticket操作は各コマンドの権限・状態条件に従います。
- **例**: `/ticket tag name:test`

## /ticket transfer

- **用途**: Claim担当者を変更します。
- **引数（*必須）**: member*:user
- **権限**: Ticket担当Staff／設定権限。現在のPanel・Team・Ticketへのアクセスを確認。
- **応答**: Ticket内への公開応答。失敗は本人向け。
- **無効時**: 受付無効は新規作成を停止します。既存Ticket操作は各コマンドの権限・状態条件に従います。
- **例**: `/ticket transfer member:@TestMember`

## /ticket unclaim

- **用途**: Claimを解除します。
- **引数（*必須）**: —
- **権限**: 自分がClaimしたTicket内。
- **応答**: Ticket内／実行Channelへの公開応答。失敗は本人向け。
- **無効時**: 受付無効は新規作成を停止します。既存Ticket操作は各コマンドの権限・状態条件に従います。
- **例**: `/ticket unclaim`

## /timeout

- **用途**: メンバーを一時的にタイムアウトします。
- **引数（*必須）**: member*:user, minutes*:integer, reason:string
- **権限**: moderate_members; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/timeout member:@TestMember minutes:5`

## /trust_score

- **用途**: メンバーの信頼度スコアと算出理由を表示します。
- **引数（*必須）**: member*:user
- **権限**: manage_guild; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/trust_score member:@TestMember`

## /userinfo

- **用途**: ユーザー情報を表示します。
- **引数（*必須）**: member:user
- **権限**: 一般メンバー（サーバーとChannelの利用権限が必要）。
- **応答**: 公開応答。エラーは本人向け。
- **無効時**: 基本コマンド。権限・実行場所などの条件は引き続き適用。
- **例**: `/userinfo`

## /vcleaderboard

- **用途**: VC XPランキングを表示します。
- **引数（*必須）**: —
- **権限**: 一般メンバー（サーバーとChannelの利用権限が必要）。
- **応答**: 公開応答。エラーは本人向け。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/vcleaderboard`

## /vcrank

- **用途**: 現在のVCレベルを確認します。
- **引数（*必須）**: —
- **権限**: 一般メンバー（サーバーとChannelの利用権限が必要）。
- **応答**: 公開応答。エラーは本人向け。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/vcrank`

## /warn

- **用途**: メンバーに警告を与えます。
- **引数（*必須）**: member*:user, reason:string
- **権限**: moderate_members; Bot permissions and role hierarchy also apply.
- **応答**: 操作結果は本人向け。処置・投稿・ログ等の効果は対象Channelや権限を持つ利用者から見えます。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/warn member:@TestMember`

## /welcome

- **用途**: ウェルカムメッセージを送信します。
- **引数（*必須）**: member:user
- **権限**: 一般メンバー。対象サーバーでWelcome機能が有効。
- **応答**: 公開応答。エラーは本人向け。
- **無効時**: 対応機能が無効な場合は新規利用できません。既存データの扱いは機能別ガイドを参照。
- **例**: `/welcome`
