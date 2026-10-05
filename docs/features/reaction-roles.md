---
feature_id: reaction_roles
title: リアクションロール
keywords: Reaction Roles normal unique verify binding drop reversed temp lock link emoji role
---

# リアクションロール

メッセージの絵文字へリアクションすると、設定に応じてロールを取得・解除できます。サーバー管理者はダッシュボードまたは `/reactionrole` コマンドで、対象メッセージと絵文字・ロールの対応を設定します。`/r` は短縮コマンドです。

## 動作方式

| 動作方式 | 追加時 | 削除時 | 特徴 |
| --- | --- | --- | --- |
| normal | ロール付与 | ロール解除 | 複数選択可能 |
| unique | 新ロールへ切替 | ロール解除 | 同じメッセージ内で1つだけ選択可能 |
| verify | ロール付与 | 維持 | 認証用途 |
| binding | 初回だけロール付与 | 設定に従う | 選択履歴をリセットするまで再選択不可 |
| drop | ロール解除 | 変更なし | ロール返却用途 |
| reversed | ロール解除 | ロール付与 | 通常と逆 |
| temp | 期限付きロール付与 | 即時解除 | 1分～365日 |
| lock | 処理停止 | 処理停止 | 元の動作方式を保持した停止状態 |

## アクセス方式と制約

Blacklist方式は指定ロールを持つメンバーの利用を拒否します。Whitelist方式は指定ロールを持つメンバーだけを許可します。両方式の同時設定はダッシュボードとAPIの両方で拒否されます。拒否一致は最優先です。

Limitは選択数、Max Rolesは実際にロールを持つメンバー数の上限です。`unique`と`binding`はlimit 1固定です。

Link Groupでは、複数のメッセージ全体から1つだけ選べるようにします。参加できる動作方式はnormal、unique、tempです。

## 絵文字

絵文字の選択画面からUnicode絵文字またはサーバー絵文字を選択します。UnicodeはNFC正規化し、カスタム絵文字はDiscordの絵文字IDで保存します。自由入力した文字列や利用できない外部絵文字は保存できません。同じメッセージ内では、絵文字とロールをそれぞれ重複して設定できません。

## 必要権限

Manage Roles、Add Reactions、Read Message History、Manage Messagesが必要です。Botのロールは付与ロールより上に配置します。メッセージやチャンネルが見えない場合はView Channelも確認します。

## ロールが付かない場合

1. ダッシュボードの診断で権限とロール階層を確認します。
2. メッセージID、チャンネル、絵文字とロールの組み合わせが現在のDiscord投稿と一致するか確認します。
3. Lock、Whitelist／Blacklist、Binding履歴、Limit、Max Rolesを確認します。
4. `fix`でBotのリアクションと設定を再同期します。
5. 外部絵文字だけ失敗する場合は`fixforeign`を使用します。

Discordイベントはサーバー・ユーザー・メッセージまたはLink Group単位でロックされ、重複イベントによる二重付与を防ぎます。
