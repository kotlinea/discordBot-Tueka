---
feature_id: welcome
title: 入退室メッセージ
keywords: Welcome Leave ようこそ 退出 テンプレート
---

# 入退室メッセージ

Memberの参加・退出時に、指定ChannelへTextまたはEmbedを送信します。参加と退出は個別に有効化できます。

## 設定

| 設定 | 必須条件 | 説明 |
| --- | --- | --- |
| Welcome有効 | 任意 | 参加通知を有効化 |
| Welcome Channel | Welcome有効時 | Text Channelから選択 |
| 表示形式 | text / embed | Discordの通常本文またはEmbed |
| Welcome本文 | Welcome有効時 | 空欄なら初期テンプレート |
| Leave有効／Channel／形式／本文 | Leave有効時 | 退出通知も同じ構成 |

TextはDiscord上限の2000文字以内、Embed Descriptionは4096文字以内です。

## テンプレート変数

設定画面に表示される変数を使用します。代表例はMember Mention、User名、Server名、Member数です。未対応の波括弧は置換されず、そのまま表示されます。

保存後はテスト参加用アカウントまたは検証環境でMentionとChannel権限を確認してください。
