---
feature_id: audit_log
title: サーバーログ
keywords: Audit Log メッセージ削除 編集 Join Leave Role Channel
---

# サーバーログ

メッセージ、Voice、Channel、Member、Role、Server設定の変化を管理Channelへ記録します。

## 設定

管理Channelを選び、必要なカテゴリだけを有効にします。Member処置の実行者を特定するにはView Audit Logが必要です。送信先ChannelではView Channel、Send Messages、Embed Linksを許可してください。

削除済みメッセージの本文を保存できるのは、Botが削除前のイベントを受信している場合だけです。Bot停止中やMessage Content Intent不足では本文を補完できません。

Moderationの検知・処置は[Moderation Logs](moderation-logs.md)へ記録されます。両方を同じChannelへ設定しても、Bot自身の処置は重複抑止されます。
