---
feature_id: moderation_logs
title: Moderation Logs
keywords: モデレーションログ ケース 監査ログ AutoMod Spam Raid
---

# Moderation Logs

AutoMod、Spam、Raid、Warning、Timeout、Kick、Ban、Lockdown、管理者操作を共通Moderation Eventとして記録します。

## ログ先

機能別ログ先が設定されていれば優先し、未設定時はModerationの既定ログ先へ送信します。Embedにはイベント番号、ケース番号、発生源、ルール、対象、チャンネル、理由、実行者、Actionの成功・失敗を含めます。

ログはDiscordのメンション通知を無効にして送信します。View Audit Log権限がある場合はDiscordの監査ログと照合し、操作した人の情報を補います。Bot自身の処置と監査ログが重複して記録されるのを防ぎます。

## 証跡

メッセージ本文は最大1000文字、添付はファイル名・種別・サイズだけを保存します。本文の保存対象は、証跡除外チャンネル以外です。保持期限後は本文を削除します。
