---
feature_id: temporary_voice
title: 一時的な音声チャンネル
keywords: Temporary Voice VC trigger category channel name template
---

# 一時的な音声チャンネル

MemberがトリガーVoice Channelへ参加すると、専用Voice Channelを作成して移動し、無人になると削除します。

| 設定 | 必須 | 説明 |
| --- | --- | --- |
| トリガーChannel | はい | DiscordのVoice Channelから選択 |
| 作成先Category | 任意 | 未設定時はトリガーと同じCategory |
| Channel名テンプレート | はい | 空欄なら初期テンプレート |

Channel名テンプレートでは設定画面に表示されるUser名などの変数を使用できます。DiscordのChannel名上限へ収まるよう正規化されます。

BotにはManage ChannelsとMove Membersが必要です。作成されない場合はトリガーがVoice Channelであること、CategoryのOverwrite、Bot Roleを確認してください。
