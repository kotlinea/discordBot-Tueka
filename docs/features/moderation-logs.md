---
feature_id: moderation_logs
title: Moderation Logs
keywords: モデレーションログ ケース 監査ログ AutoMod Spam Raid
---

# Moderation Logs

AutoMod、Spam、Raid、Warning、Timeout、Kick、Ban、Lockdown、管理者操作を共通Moderation Eventとして記録します。

## ログ先

機能別ログ先が設定されていれば優先し、未設定時はModerationの既定ログ先へ送信します。Embedにはイベント番号、ケース番号、発生源、ルール、対象、Channel、理由、実行者、Actionの成功・失敗を含めます。

Discord Mentionは無効化して送信します。View Audit Log権限がある場合、Discord監査ログと突合して実行者を補完します。Bot自身のActionと監査ログの重複は抑止します。

## 証跡

メッセージ本文は最大1000文字、添付はファイル名・種別・サイズだけを保存します。証跡除外Channelでは本文を保存しません。保持期限後は本文を削除します。
