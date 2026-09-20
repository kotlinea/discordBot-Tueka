---
feature_id: advanced_polls
title: 拡張投票
keywords: Poll 投票 ボタン 期限 画像
---

# 拡張投票

サーバー管理権限（Manage Server）を持つ利用者が `/poll` でButton投票を作成します。実行したチャンネルに投稿されます。質問は256文字以内、選択肢は `|` 区切りで2～10件、各70文字以内です。

BotにはView Channel、Send Messages、Embed Linksが必要です。任意のduration_minutesで期限を1～10080分に設定し、image_urlでHTTP／HTTPSの画像を指定できます。

終了後は結果を確定し、Button操作を停止します。投稿Messageが削除された場合、投票データが残っていてもDiscord上の表示は復元されません。
