---
feature_id: advanced_polls
title: 拡張投票
keywords: Poll 投票 ボタン 期限 画像
---

# 拡張投票

最大10個の選択肢、期限、画像を持つButton投票を作成します。作成者は質問、選択肢、終了条件、表示Channelを指定します。

BotにはView Channel、Send Messages、Embed Linksが必要です。Discord Application Commandの入力上限を超える詳細設定はModalで入力します。

終了後は結果を確定し、Button操作を停止します。投稿Messageが削除された場合、投票データが残っていてもDiscord上の表示は復元されません。
