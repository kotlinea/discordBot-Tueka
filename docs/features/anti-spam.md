---
feature_id: anti_spam
title: Anti-Spam
keywords: 連投 同一メッセージ メンションスパム リアクションスパム Bot Webhook
---

# Anti-Spam

時間窓内の投稿・リアクションをユーザー単位で集計し、連投や大量操作を検知します。

## Trigger

| Trigger | 判定内容 |
| --- | --- |
| message_rate | 指定秒数内のメッセージ数 |
| duplicate | 同一または類似内容の連投 |
| mention_rate | User／Role Mention数 |
| link_rate | URLを含む投稿数 |
| attachment_rate | 添付を含む投稿数 |
| reaction_rate | リアクション追加数 |
| reaction_burst | 同一メッセージへの短時間連打 |

指定した時間窓の開始時刻を含めて集計します。メッセージの編集時は、その投稿のカウントを維持します。

## 段階的な制裁

最初の検知で最近の投稿を削除してWarningを加算し、pointsの閾値横断を[Warnings / Infractions](infractions.md)でTimeoutやBanへ接続できます。同時に複数閾値を越えた場合は最高段階だけを実行します。

Bot／Webhookは既定で対象外です。連携Botの暴走を監視する場合は、actor種別と対象Channelを明示した専用ルールを作成してください。

ルールの作成・複製・一括ON/OFFは[ルール操作ガイド](../dashboard/moderation-rules.md)を参照してください。
