---
feature_id: reaction_roles
title: リアクションロール
keywords: Reaction Roles normal unique verify binding drop reversed temp lock link emoji role
---

# リアクションロール

メッセージのEmojiへリアクションすると、設定に応じてRoleを取得・解除できます。サーバー管理者はDashboardまたは `/reactionrole` コマンドで、対象メッセージとEmoji・Roleの対応を設定します。`/r` は短縮コマンドです。

## 動作Type

| Type | 追加時 | 削除時 | 特徴 |
| --- | --- | --- | --- |
| normal | Role付与 | Role解除 | 複数選択可能 |
| unique | 新Roleへ切替 | Role解除 | 同一Message内で1択 |
| verify | Role付与 | 維持 | 認証用途 |
| binding | 初回だけRole付与 | 設定に従う | 選択履歴をResetするまで再選択不可 |
| drop | Role解除 | 変更なし | Role返却用途 |
| reversed | Role解除 | Role付与 | 通常と逆 |
| temp | 期限付きRole付与 | 即時解除 | 1分～365日 |
| lock | 処理停止 | 処理停止 | 元Typeを保持した停止状態 |

## アクセス方式と制約

Blacklist方式は指定Roleを拒否します。Whitelist方式は指定Roleを持つMemberだけを許可します。両方式の同時設定はDashboardとAPIの両方で拒否されます。拒否一致は最優先です。

Limitは選択数、Max Rolesは実際にRoleを持つMember数の上限です。`unique`と`binding`はlimit 1固定です。

Link Groupは複数Messageをまたいだ1択を作ります。参加できるTypeはnormal、unique、tempです。

## Emoji

Emoji PickerからUnicode EmojiまたはサーバーEmojiを選択します。UnicodeはNFC正規化し、Custom EmojiはDiscord Emoji IDで保存します。自由入力した文字列や利用できない外部Emojiは保存できません。同じMessageでEmojiとRoleはそれぞれ一意です。

## 必要権限

Manage Roles、Add Reactions、Read Message History、Manage Messagesが必要です。Bot Roleは付与Roleより上に配置します。MessageまたはChannelが見えない場合はView Channelも確認します。

## Roleが付かない場合

1. Dashboardの診断で権限とRole階層を確認します。
2. Message ID、Channel、Emoji対応が現在のDiscord投稿と一致するか確認します。
3. Lock、Whitelist／Blacklist、Binding履歴、Limit、Max Rolesを確認します。
4. `fix`でBotのリアクションと設定を再同期します。
5. 外部Emojiだけ失敗する場合は`fixforeign`を使用します。

DiscordイベントはGuild・User・MessageまたはLink Group単位でロックされ、重複イベントによる二重付与を防ぎます。
